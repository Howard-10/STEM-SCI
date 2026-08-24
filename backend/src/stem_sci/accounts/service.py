"""SQLite-backed identity service for the first multi-user backend slice."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import uuid4

from .models import (
    AuthTokenPair,
    LoginRequest,
    ProjectCreateRequest,
    ProjectPatchRequest,
    ResearchProject,
    TokenRefreshRequest,
    UserCreateRequest,
    UserProfile,
)

ACCESS_TOKEN_SECONDS = 60 * 60
REFRESH_TOKEN_SECONDS = 60 * 60 * 24 * 14
PASSWORD_ITERATIONS = 200_000


@dataclass(frozen=True)
class AuthError(Exception):
    """Expected authentication or authorization failure."""

    status_code: int
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


class IdentityService:
    """Owns users, opaque sessions, and project membership.

    The service intentionally uses opaque random tokens instead of JWTs so the
    backend can revoke sessions without adding another dependency.
    """

    def __init__(self, database: Path) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def register(self, request: UserCreateRequest) -> AuthTokenPair:
        now = _utc_now()
        user_id = f"user-{uuid4().hex}"
        password_hash = _hash_password(request.password)
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    insert into users(user_id, username, email, display_name, password_hash, created_at)
                    values (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        request.username.strip(),
                        request.email.strip().lower(),
                        request.display_name.strip() if request.display_name else None,
                        password_hash,
                        _dt(now),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise AuthError(400, "user_already_exists", "Username or email is already registered") from exc
        return self._issue_tokens(self.get_user(user_id))

    def login(self, request: LoginRequest) -> AuthTokenPair:
        row = self._user_row_by_login(request.login)
        if row is None or not _verify_password(request.password, str(row["password_hash"])):
            raise AuthError(401, "invalid_credentials", "Invalid username/email or password")
        return self._issue_tokens(_profile(row))

    def refresh(self, request: TokenRefreshRequest) -> AuthTokenPair:
        token_hash = _token_hash(request.refresh_token)
        now = _utc_now()
        with self._connect() as connection:
            row = connection.execute(
                """
                select s.session_id, s.user_id, s.refresh_expires_at, s.revoked_at,
                       u.username, u.email, u.display_name, u.created_at
                from user_sessions s
                join users u on u.user_id=s.user_id
                where s.refresh_token_hash=?
                """,
                (token_hash,),
            ).fetchone()
            if row is None or row["revoked_at"] is not None or _parse_dt(row["refresh_expires_at"]) <= now:
                raise AuthError(401, "invalid_refresh_token", "Refresh token is invalid or expired")
            connection.execute(
                "update user_sessions set revoked_at=? where session_id=?",
                (_dt(now), row["session_id"]),
            )
        return self._issue_tokens(_profile(row))

    def logout(self, access_token: str) -> None:
        token_hash = _token_hash(access_token)
        with self._connect() as connection:
            connection.execute(
                """
                update user_sessions set revoked_at=?
                where access_token_hash=? and revoked_at is null
                """,
                (_dt(_utc_now()), token_hash),
            )

    def user_for_access_token(self, access_token: str) -> UserProfile:
        token_hash = _token_hash(access_token)
        now = _utc_now()
        with self._connect() as connection:
            row = connection.execute(
                """
                select s.expires_at, s.revoked_at,
                       u.user_id, u.username, u.email, u.display_name, u.created_at
                from user_sessions s
                join users u on u.user_id=s.user_id
                where s.access_token_hash=?
                """,
                (token_hash,),
            ).fetchone()
        if row is None or row["revoked_at"] is not None or _parse_dt(row["expires_at"]) <= now:
            raise AuthError(401, "invalid_access_token", "Access token is invalid or expired")
        return _profile(row)

    def get_user(self, user_id: str) -> UserProfile:
        with self._connect() as connection:
            row = connection.execute(
                """
                select user_id, username, email, display_name, created_at
                from users where user_id=?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            raise AuthError(404, "user_not_found", "User was not found")
        return _profile(row)

    def create_project(self, user: UserProfile, request: ProjectCreateRequest) -> ResearchProject:
        now = _utc_now()
        project_id = request.project_id or f"project-{uuid4().hex[:16]}"
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    insert into research_projects(
                        project_id, owner_user_id, title, research_direction,
                        abstract, status, created_at, updated_at
                    )
                    values (?, ?, ?, ?, ?, 'active', ?, ?)
                    """,
                    (
                        project_id,
                        user.user_id,
                        request.title.strip(),
                        request.research_direction.strip(),
                        request.abstract.strip() if request.abstract else None,
                        _dt(now),
                        _dt(now),
                    ),
                )
                connection.execute(
                    """
                    insert into project_members(project_id, user_id, role, created_at)
                    values (?, ?, 'owner', ?)
                    """,
                    (project_id, user.user_id, _dt(now)),
                )
        except sqlite3.IntegrityError as exc:
            raise AuthError(400, "project_already_exists", "Project id already exists") from exc
        return self.get_project(user, project_id)

    def list_projects(self, user: UserProfile) -> list[ResearchProject]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                select p.project_id, p.owner_user_id, p.title, p.research_direction,
                       p.abstract, p.status, p.created_at, p.updated_at, m.role
                from research_projects p
                join project_members m on m.project_id=p.project_id
                where m.user_id=? and p.deleted_at is null
                order by p.updated_at desc, p.created_at desc
                """,
                (user.user_id,),
            ).fetchall()
        return [_project(row) for row in rows]

    def get_project(self, user: UserProfile, project_id: str) -> ResearchProject:
        row = self._project_row_for_user(user.user_id, project_id)
        if row is None:
            raise AuthError(404, "project_not_found", "Project was not found")
        return _project(row)

    def patch_project(
        self, user: UserProfile, project_id: str, request: ProjectPatchRequest
    ) -> ResearchProject:
        current = self.get_project(user, project_id)
        if current.role not in {"owner", "editor"}:
            raise AuthError(403, "project_forbidden", "Project membership cannot edit this project")
        updates: dict[str, object] = {}
        if request.title is not None:
            updates["title"] = request.title.strip()
        if request.research_direction is not None:
            updates["research_direction"] = request.research_direction.strip()
        if request.abstract is not None:
            updates["abstract"] = request.abstract.strip()
        if request.status is not None:
            updates["status"] = request.status
        if updates:
            updates["updated_at"] = _dt(_utc_now())
            assignments = ", ".join(f"{name}=?" for name in updates)
            with self._connect() as connection:
                connection.execute(
                    f"update research_projects set {assignments} where project_id=?",
                    (*updates.values(), project_id),
                )
        return self.get_project(user, project_id)

    def delete_project(self, user: UserProfile, project_id: str) -> None:
        current = self.get_project(user, project_id)
        if current.role != "owner":
            raise AuthError(403, "project_forbidden", "Only the project owner can delete it")
        now = _dt(_utc_now())
        with self._connect() as connection:
            connection.execute(
                "update research_projects set deleted_at=?, updated_at=? where project_id=?",
                (now, now, project_id),
            )

    def _issue_tokens(self, user: UserProfile) -> AuthTokenPair:
        now = _utc_now()
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(48)
        expires_at = now + timedelta(seconds=ACCESS_TOKEN_SECONDS)
        refresh_expires_at = now + timedelta(seconds=REFRESH_TOKEN_SECONDS)
        with self._connect() as connection:
            connection.execute(
                """
                insert into user_sessions(
                    session_id, user_id, access_token_hash, refresh_token_hash,
                    created_at, expires_at, refresh_expires_at
                )
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"session-{uuid4().hex}",
                    user.user_id,
                    _token_hash(access_token),
                    _token_hash(refresh_token),
                    _dt(now),
                    _dt(expires_at),
                    _dt(refresh_expires_at),
                ),
            )
        return AuthTokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=ACCESS_TOKEN_SECONDS,
            user=user,
        )

    def _project_row_for_user(self, user_id: str, project_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                select p.project_id, p.owner_user_id, p.title, p.research_direction,
                       p.abstract, p.status, p.created_at, p.updated_at, m.role
                from research_projects p
                join project_members m on m.project_id=p.project_id
                where p.project_id=? and m.user_id=? and p.deleted_at is null
                """,
                (project_id, user_id),
            ).fetchone()
            return cast(sqlite3.Row | None, row)

    def _user_row_by_login(self, login: str) -> sqlite3.Row | None:
        normalized = login.strip().lower()
        with self._connect() as connection:
            row = connection.execute(
                """
                select user_id, username, email, display_name, password_hash, created_at
                from users
                where lower(username)=? or lower(email)=?
                """,
                (normalized, normalized),
            ).fetchone()
            return cast(sqlite3.Row | None, row)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("pragma foreign_keys = on")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute("pragma foreign_keys = on")
            connection.execute(
                """
                create table if not exists users (
                    user_id text primary key,
                    username text not null unique,
                    email text not null unique,
                    display_name text,
                    password_hash text not null,
                    created_at text not null
                )
                """
            )
            connection.execute(
                """
                create table if not exists user_sessions (
                    session_id text primary key,
                    user_id text not null references users(user_id),
                    access_token_hash text not null unique,
                    refresh_token_hash text not null unique,
                    created_at text not null,
                    expires_at text not null,
                    refresh_expires_at text not null,
                    revoked_at text
                )
                """
            )
            connection.execute(
                """
                create table if not exists research_projects (
                    project_id text primary key,
                    owner_user_id text not null references users(user_id),
                    title text not null,
                    research_direction text not null,
                    abstract text,
                    status text not null,
                    created_at text not null,
                    updated_at text not null,
                    deleted_at text
                )
                """
            )
            connection.execute(
                """
                create table if not exists project_members (
                    project_id text not null references research_projects(project_id),
                    user_id text not null references users(user_id),
                    role text not null,
                    created_at text not null,
                    primary key(project_id, user_id)
                )
                """
            )


def _profile(row: sqlite3.Row) -> UserProfile:
    return UserProfile(
        user_id=str(row["user_id"]),
        username=str(row["username"]),
        email=str(row["email"]),
        display_name=row["display_name"],
        created_at=_parse_dt(row["created_at"]),
    )


def _project(row: sqlite3.Row) -> ResearchProject:
    return ResearchProject(
        project_id=str(row["project_id"]),
        owner_user_id=str(row["owner_user_id"]),
        title=str(row["title"]),
        research_direction=str(row["research_direction"]),
        abstract=row["abstract"],
        status=row["status"],
        role=row["role"],
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$", maxsplit=3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _dt(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

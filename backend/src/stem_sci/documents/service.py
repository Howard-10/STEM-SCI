"""Versioned project-document storage on local filesystem plus SQLite metadata."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from stem_sci.accounts import UserProfile

from .models import (
    DocumentCreateRequest,
    DocumentPatchRequest,
    DocumentVersion,
    DocumentVersionCreateRequest,
    ProjectDocument,
)


@dataclass(frozen=True)
class DocumentError(Exception):
    status_code: int
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


class DocumentService:
    """Stores project documents as append-only versions.

    Metadata lives in SQLite. Version content is written to the storage root so
    later deployments can swap this for object storage without changing API
    contracts.
    """

    def __init__(self, database: Path, storage_root: Path) -> None:
        self.database = database
        self.storage_root = storage_root
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def create(
        self,
        *,
        project_id: str,
        user: UserProfile,
        request: DocumentCreateRequest,
    ) -> ProjectDocument:
        now = _utc_now()
        document_id = f"doc-{uuid4().hex}"
        encoded = request.content.encode("utf-8")
        digest = _sha256(encoded)
        storage_ref = self._write_version(
            project_id=project_id,
            document_id=document_id,
            version=1,
            suffix=self._suffix(request.format),
            content=encoded,
        )
        with self._connect() as connection:
            connection.execute(
                """
                insert into project_documents(
                    document_id, project_id, title, document_type, format, status,
                    current_version, current_sha256, size_bytes, created_by,
                    updated_by, created_at, updated_at
                )
                values (?, ?, ?, ?, ?, 'active', 1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    project_id,
                    request.title.strip(),
                    request.document_type,
                    request.format,
                    digest,
                    len(encoded),
                    user.user_id,
                    user.user_id,
                    _dt(now),
                    _dt(now),
                ),
            )
            connection.execute(
                """
                insert into project_document_versions(
                    document_id, project_id, version, format, storage_ref, sha256,
                    size_bytes, change_note, created_by, created_at
                )
                values (?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    project_id,
                    request.format,
                    storage_ref,
                    digest,
                    len(encoded),
                    request.change_note,
                    user.user_id,
                    _dt(now),
                ),
            )
        return self.get(project_id, document_id)

    def list_project(self, project_id: str) -> list[ProjectDocument]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                select * from project_documents
                where project_id=? and deleted_at is null
                order by updated_at desc, created_at desc
                """,
                (project_id,),
            ).fetchall()
        return [_document(row) for row in rows]

    def get(self, project_id: str, document_id: str) -> ProjectDocument:
        row = self._document_row(project_id, document_id)
        if row is None:
            raise DocumentError(404, "document_not_found", "Document was not found")
        return _document(row)

    def patch(
        self,
        *,
        project_id: str,
        document_id: str,
        user: UserProfile,
        request: DocumentPatchRequest,
    ) -> ProjectDocument:
        self.get(project_id, document_id)
        updates: dict[str, object] = {}
        if request.title is not None:
            updates["title"] = request.title.strip()
        if request.document_type is not None:
            updates["document_type"] = request.document_type
        if request.status is not None:
            updates["status"] = request.status
        if updates:
            updates["updated_by"] = user.user_id
            updates["updated_at"] = _dt(_utc_now())
            assignments = ", ".join(f"{name}=?" for name in updates)
            with self._connect() as connection:
                connection.execute(
                    f"update project_documents set {assignments} where project_id=? and document_id=?",
                    (*updates.values(), project_id, document_id),
                )
        return self.get(project_id, document_id)

    def delete(self, *, project_id: str, document_id: str, user: UserProfile) -> None:
        self.get(project_id, document_id)
        now = _dt(_utc_now())
        with self._connect() as connection:
            connection.execute(
                """
                update project_documents
                set deleted_at=?, updated_at=?, updated_by=?
                where project_id=? and document_id=?
                """,
                (now, now, user.user_id, project_id, document_id),
            )

    def create_version(
        self,
        *,
        project_id: str,
        document_id: str,
        user: UserProfile,
        request: DocumentVersionCreateRequest,
    ) -> DocumentVersion:
        document = self.get(project_id, document_id)
        next_version = document.current_version + 1
        now = _utc_now()
        encoded = request.content.encode("utf-8")
        digest = _sha256(encoded)
        storage_ref = self._write_version(
            project_id=project_id,
            document_id=document_id,
            version=next_version,
            suffix=self._suffix(document.format),
            content=encoded,
        )
        with self._connect() as connection:
            connection.execute(
                """
                insert into project_document_versions(
                    document_id, project_id, version, format, storage_ref, sha256,
                    size_bytes, change_note, created_by, created_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    project_id,
                    next_version,
                    document.format,
                    storage_ref,
                    digest,
                    len(encoded),
                    request.change_note,
                    user.user_id,
                    _dt(now),
                ),
            )
            connection.execute(
                """
                update project_documents
                set current_version=?, current_sha256=?, size_bytes=?,
                    updated_by=?, updated_at=?
                where project_id=? and document_id=?
                """,
                (
                    next_version,
                    digest,
                    len(encoded),
                    user.user_id,
                    _dt(now),
                    project_id,
                    document_id,
                ),
            )
        return self.get_version(project_id, document_id, next_version)

    def list_versions(self, project_id: str, document_id: str) -> list[DocumentVersion]:
        self.get(project_id, document_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                select * from project_document_versions
                where project_id=? and document_id=?
                order by version desc
                """,
                (project_id, document_id),
            ).fetchall()
        return [self._version(row) for row in rows]

    def get_version(self, project_id: str, document_id: str, version: int) -> DocumentVersion:
        self.get(project_id, document_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                select * from project_document_versions
                where project_id=? and document_id=? and version=?
                """,
                (project_id, document_id, version),
            ).fetchone()
        if row is None:
            raise DocumentError(404, "document_version_not_found", "Document version was not found")
        return self._version(row)

    def _version(self, row: sqlite3.Row) -> DocumentVersion:
        content_path = self._resolve_storage_ref(str(row["storage_ref"]))
        try:
            content = content_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DocumentError(500, "document_content_missing", "Document content is missing") from exc
        encoded = content.encode("utf-8")
        if _sha256(encoded) != row["sha256"]:
            raise DocumentError(500, "document_hash_mismatch", "Document content hash mismatch")
        return DocumentVersion(
            document_id=str(row["document_id"]),
            project_id=str(row["project_id"]),
            version=int(row["version"]),
            format=row["format"],
            content=content,
            sha256=str(row["sha256"]),
            size_bytes=int(row["size_bytes"]),
            storage_ref=str(row["storage_ref"]),
            change_note=row["change_note"],
            created_by=str(row["created_by"]),
            created_at=_parse_dt(row["created_at"]),
        )

    def _document_row(self, project_id: str, document_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                select * from project_documents
                where project_id=? and document_id=? and deleted_at is null
                """,
                (project_id, document_id),
            ).fetchone()
            return cast(sqlite3.Row | None, row)

    def _write_version(
        self,
        *,
        project_id: str,
        document_id: str,
        version: int,
        suffix: str,
        content: bytes,
    ) -> str:
        directory = self.storage_root / _safe_bucket(project_id) / document_id
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"v{version}{suffix}"
        path = (directory / filename).resolve()
        storage_root = self.storage_root.resolve()
        if storage_root not in path.parents:
            raise DocumentError(400, "invalid_document_storage_ref", "Document storage path is invalid")
        path.write_bytes(content)
        return str(path.relative_to(storage_root).as_posix())

    def _resolve_storage_ref(self, storage_ref: str) -> Path:
        storage_root = self.storage_root.resolve()
        path = (storage_root / storage_ref).resolve()
        if storage_root not in path.parents:
            raise DocumentError(400, "invalid_document_storage_ref", "Document storage path is invalid")
        return path

    @staticmethod
    def _suffix(format_value: str) -> str:
        return {
            "markdown": ".md",
            "text": ".txt",
            "pdf": ".pdf",
            "docx": ".docx",
            "csv": ".csv",
        }.get(format_value, ".txt")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
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
            connection.execute(
                """
                create table if not exists project_documents (
                    document_id text not null,
                    project_id text not null,
                    title text not null,
                    document_type text not null,
                    format text not null,
                    status text not null,
                    current_version integer not null,
                    current_sha256 text not null,
                    size_bytes integer not null,
                    created_by text not null,
                    updated_by text not null,
                    created_at text not null,
                    updated_at text not null,
                    deleted_at text,
                    primary key(project_id, document_id)
                )
                """
            )
            connection.execute(
                """
                create table if not exists project_document_versions (
                    document_id text not null,
                    project_id text not null,
                    version integer not null,
                    format text not null,
                    storage_ref text not null,
                    sha256 text not null,
                    size_bytes integer not null,
                    change_note text,
                    created_by text not null,
                    created_at text not null,
                    primary key(project_id, document_id, version)
                )
                """
            )


def _document(row: sqlite3.Row) -> ProjectDocument:
    return ProjectDocument(
        document_id=str(row["document_id"]),
        project_id=str(row["project_id"]),
        title=str(row["title"]),
        document_type=row["document_type"],
        format=row["format"],
        status=row["status"],
        current_version=int(row["current_version"]),
        current_sha256=str(row["current_sha256"]),
        size_bytes=int(row["size_bytes"]),
        created_by=str(row["created_by"]),
        updated_by=str(row["updated_by"]),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_bucket(project_id: str) -> str:
    return hashlib.sha256(project_id.encode("utf-8")).hexdigest()[:16]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _dt(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

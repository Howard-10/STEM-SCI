"""Project-scoped storage for structured artifact bodies."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from stem_sci.utils.hash_utils import sha256_text


class ArtifactContent(BaseModel):
    """A versioned JSON body stored behind an ``ArtifactRef``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    artifact_type: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    body: dict[str, JsonValue]
    content_hash: str | None = Field(default=None, min_length=64, max_length=64)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def set_or_validate_hash(self) -> ArtifactContent:
        expected = _body_hash(self.body)
        if self.content_hash is None:
            object.__setattr__(self, "content_hash", expected)
        elif self.content_hash != expected:
            raise ValueError("content_hash does not match canonical body")
        return self

    def validate_integrity(self) -> None:
        if self.content_hash != _body_hash(self.body):
            raise ValueError("content_hash does not match canonical body")


class ArtifactContentStore(Protocol):
    def put(self, content: ArtifactContent) -> ArtifactContent: ...

    def get(
        self, project_id: str, artifact_id: str, version: int | None = None
    ) -> ArtifactContent | None: ...

    def list_versions(self, project_id: str, artifact_id: str) -> list[ArtifactContent]: ...

    def list_project(self, project_id: str) -> list[ArtifactContent]: ...


class InMemoryArtifactContentStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str, int], ArtifactContent] = {}

    def put(self, content: ArtifactContent) -> ArtifactContent:
        content.validate_integrity()
        self._items[(content.project_id, content.artifact_id, content.version)] = content
        return content

    def get(
        self, project_id: str, artifact_id: str, version: int | None = None
    ) -> ArtifactContent | None:
        matches = [
            item
            for (item_project, item_id, item_version), item in self._items.items()
            if item_project == project_id
            and item_id == artifact_id
            and (version is None or item_version == version)
        ]
        return max(matches, key=lambda item: item.version) if matches else None

    def list_versions(self, project_id: str, artifact_id: str) -> list[ArtifactContent]:
        return sorted(
            [
                item
                for (item_project, item_id, _), item in self._items.items()
                if item_project == project_id and item_id == artifact_id
            ],
            key=lambda item: item.version,
        )

    def list_project(self, project_id: str) -> list[ArtifactContent]:
        return sorted(
            [item for (item_project, _, _), item in self._items.items() if item_project == project_id],
            key=lambda item: (item.artifact_id, item.version),
        )


class SQLiteArtifactContentStore:
    """SQLite-backed artifact bodies sharing the workflow database."""

    def __init__(self, database: Path) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                create table if not exists workflow_artifact_contents (
                    project_id text not null,
                    artifact_id text not null,
                    version integer not null,
                    body text not null,
                    primary key (project_id, artifact_id, version)
                )
                """
            )

    def put(self, content: ArtifactContent) -> ArtifactContent:
        content.validate_integrity()
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                insert into workflow_artifact_contents(project_id, artifact_id, version, body)
                values (?, ?, ?, ?)
                on conflict(project_id, artifact_id, version) do update set body=excluded.body
                """,
                (
                    content.project_id,
                    content.artifact_id,
                    content.version,
                    content.model_dump_json(),
                ),
            )
        return content

    def get(
        self, project_id: str, artifact_id: str, version: int | None = None
    ) -> ArtifactContent | None:
        query = "select body from workflow_artifact_contents where project_id=? and artifact_id=?"
        params: tuple[object, ...] = (project_id, artifact_id)
        if version is None:
            query += " order by version desc limit 1"
        else:
            query += " and version=?"
            params += (version,)
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(query, params).fetchone()
        return ArtifactContent.model_validate_json(row[0]) if row is not None else None

    def list_versions(self, project_id: str, artifact_id: str) -> list[ArtifactContent]:
        with sqlite3.connect(self.database) as connection:
            rows = connection.execute(
                """
                select body from workflow_artifact_contents
                where project_id=? and artifact_id=? order by version
                """,
                (project_id, artifact_id),
            ).fetchall()
        return [ArtifactContent.model_validate_json(row[0]) for row in rows]

    def list_project(self, project_id: str) -> list[ArtifactContent]:
        with sqlite3.connect(self.database) as connection:
            rows = connection.execute(
                """
                select body from workflow_artifact_contents
                where project_id=? order by artifact_id, version
                """,
                (project_id,),
            ).fetchall()
        return [ArtifactContent.model_validate_json(row[0]) for row in rows]


def _body_hash(body: dict[str, JsonValue]) -> str:
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(canonical)

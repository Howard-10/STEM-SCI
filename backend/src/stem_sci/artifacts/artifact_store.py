"""Project-scoped artifact storage interfaces and in-memory implementation."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Protocol

from .models import ArtifactRef


class ArtifactStore(Protocol):
    def put(self, artifact: ArtifactRef) -> ArtifactRef: ...

    def get(self, project_id: str, artifact_id: str, version: int | None = None) -> ArtifactRef | None: ...

    def list_versions(self, project_id: str, artifact_id: str) -> list[ArtifactRef]: ...

    def list_project(self, project_id: str) -> list[ArtifactRef]: ...


class InMemoryArtifactStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str, int], ArtifactRef] = {}

    def put(self, artifact: ArtifactRef) -> ArtifactRef:
        key = (artifact.project_id, artifact.artifact_id, artifact.version)
        self._items[key] = artifact
        return artifact

    def get(self, project_id: str, artifact_id: str, version: int | None = None) -> ArtifactRef | None:
        matches = [
            item
            for (item_project, item_id, item_version), item in self._items.items()
            if item_project == project_id and item_id == artifact_id and (version is None or item_version == version)
        ]
        return max(matches, key=lambda item: item.version) if matches else None

    def list_versions(self, project_id: str, artifact_id: str) -> list[ArtifactRef]:
        matches = [
            item
            for (item_project, item_id, _), item in self._items.items()
            if item_project == project_id and item_id == artifact_id
        ]
        return sorted(matches, key=lambda item: item.version)

    def list_project(self, project_id: str) -> list[ArtifactRef]:
        return sorted(
            [item for (item_project, _, _), item in self._items.items() if item_project == project_id],
            key=lambda item: (item.artifact_id, item.version),
        )


class SQLiteArtifactStore:
    """SQLite-backed versioned candidate artifact references."""

    def __init__(self, database: Path) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                create table if not exists workflow_artifacts (
                    project_id text not null,
                    artifact_id text not null,
                    version integer not null,
                    body text not null,
                    primary key (project_id, artifact_id, version)
                )
                """
            )

    def put(self, artifact: ArtifactRef) -> ArtifactRef:
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                insert into workflow_artifacts(project_id, artifact_id, version, body)
                values (?, ?, ?, ?)
                on conflict(project_id, artifact_id, version) do update set body=excluded.body
                """,
                (
                    artifact.project_id,
                    artifact.artifact_id,
                    artifact.version,
                    artifact.model_dump_json(),
                ),
            )
        return artifact

    def get(self, project_id: str, artifact_id: str, version: int | None = None) -> ArtifactRef | None:
        query = "select body from workflow_artifacts where project_id=? and artifact_id=?"
        params: tuple[object, ...] = (project_id, artifact_id)
        if version is not None:
            query += " and version=?"
            params += (version,)
        else:
            query += " order by version desc limit 1"
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(query, params).fetchone()
        return ArtifactRef.model_validate_json(row[0]) if row is not None else None

    def list_versions(self, project_id: str, artifact_id: str) -> list[ArtifactRef]:
        with sqlite3.connect(self.database) as connection:
            rows = connection.execute(
                """
                select body from workflow_artifacts
                where project_id=? and artifact_id=? order by version
                """,
                (project_id, artifact_id),
            ).fetchall()
        return [ArtifactRef.model_validate_json(row[0]) for row in rows]

    def list_project(self, project_id: str) -> list[ArtifactRef]:
        with sqlite3.connect(self.database) as connection:
            rows = connection.execute(
                """
                select body from workflow_artifacts
                where project_id=? order by artifact_id, version
                """,
                (project_id,),
            ).fetchall()
        return [ArtifactRef.model_validate_json(row[0]) for row in rows]

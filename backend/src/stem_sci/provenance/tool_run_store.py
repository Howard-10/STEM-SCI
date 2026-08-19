"""Project-scoped persistence for Controller-mediated Tool runs."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Protocol

from stem_sci.tools.models import ToolRunRecord


class ToolRunStore(Protocol):
    def put(self, record: ToolRunRecord) -> ToolRunRecord: ...

    def get(self, project_id: str, tool_run_id: str) -> ToolRunRecord | None: ...

    def list_project(self, project_id: str) -> list[ToolRunRecord]: ...


class InMemoryToolRunStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], ToolRunRecord] = {}

    def put(self, record: ToolRunRecord) -> ToolRunRecord:
        self._items[(record.project_id, record.tool_run_id)] = record
        return record

    def get(self, project_id: str, tool_run_id: str) -> ToolRunRecord | None:
        return self._items.get((project_id, tool_run_id))

    def list_project(self, project_id: str) -> list[ToolRunRecord]:
        return sorted(
            [
                record
                for (record_project, _), record in self._items.items()
                if record_project == project_id
            ],
            key=lambda record: record.tool_run_id,
        )


class SQLiteToolRunStore:
    """SQLite-backed ToolRun provenance with project-isolated queries."""

    def __init__(self, database: Path) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                create table if not exists workflow_tool_runs (
                    project_id text not null,
                    tool_run_id text not null,
                    body text not null,
                    primary key (project_id, tool_run_id)
                )
                """
            )

    def put(self, record: ToolRunRecord) -> ToolRunRecord:
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                insert into workflow_tool_runs(project_id, tool_run_id, body)
                values (?, ?, ?)
                on conflict(project_id, tool_run_id) do update set body=excluded.body
                """,
                (record.project_id, record.tool_run_id, record.model_dump_json()),
            )
        return record

    def get(self, project_id: str, tool_run_id: str) -> ToolRunRecord | None:
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(
                "select body from workflow_tool_runs where project_id=? and tool_run_id=?",
                (project_id, tool_run_id),
            ).fetchone()
        return ToolRunRecord.model_validate_json(row[0]) if row is not None else None

    def list_project(self, project_id: str) -> list[ToolRunRecord]:
        with sqlite3.connect(self.database) as connection:
            rows = connection.execute(
                """
                select body from workflow_tool_runs
                where project_id=? order by tool_run_id
                """,
                (project_id,),
            ).fetchall()
        return [ToolRunRecord.model_validate_json(row[0]) for row in rows]


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

    def get_by_request(self, project_id: str, request_ref: str) -> ToolRunRecord | None: ...

    def get_by_idempotency(
        self, project_id: str, idempotency_key: str
    ) -> ToolRunRecord | None: ...


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

    def get_by_request(self, project_id: str, request_ref: str) -> ToolRunRecord | None:
        return next(
            (
                record
                for (record_project, _), record in self._items.items()
                if record_project == project_id and record.request_ref == request_ref
            ),
            None,
        )

    def get_by_idempotency(
        self, project_id: str, idempotency_key: str
    ) -> ToolRunRecord | None:
        return next(
            (
                record
                for (record_project, _), record in self._items.items()
                if record_project == project_id
                and record.idempotency_key == idempotency_key
            ),
            None,
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
                    request_ref text,
                    idempotency_key text,
                    body text not null,
                    primary key (project_id, tool_run_id)
                )
                """
            )
            columns = {
                row[1]
                for row in connection.execute("pragma table_info(workflow_tool_runs)").fetchall()
            }
            if "request_ref" not in columns:
                connection.execute(
                    "alter table workflow_tool_runs add column request_ref text"
                )
            if "idempotency_key" not in columns:
                connection.execute(
                    "alter table workflow_tool_runs add column idempotency_key text"
                )
            connection.execute(
                """
                create index if not exists workflow_tool_runs_request
                on workflow_tool_runs(project_id, request_ref)
                """
            )
            connection.execute(
                """
                create unique index if not exists workflow_tool_runs_idempotency
                on workflow_tool_runs(project_id, idempotency_key)
                where idempotency_key is not null
                """
            )

    def put(self, record: ToolRunRecord) -> ToolRunRecord:
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                insert into workflow_tool_runs(
                    project_id, tool_run_id, request_ref, idempotency_key, body
                )
                values (?, ?, ?, ?, ?)
                on conflict(project_id, tool_run_id) do update set
                    request_ref=excluded.request_ref,
                    idempotency_key=excluded.idempotency_key,
                    body=excluded.body
                """,
                (
                    record.project_id,
                    record.tool_run_id,
                    record.request_ref,
                    record.idempotency_key,
                    record.model_dump_json(),
                ),
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

    def get_by_request(self, project_id: str, request_ref: str) -> ToolRunRecord | None:
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(
                """
                select body from workflow_tool_runs
                where project_id=? and request_ref=? order by tool_run_id limit 1
                """,
                (project_id, request_ref),
            ).fetchone()
        return ToolRunRecord.model_validate_json(row[0]) if row is not None else None

    def get_by_idempotency(
        self, project_id: str, idempotency_key: str
    ) -> ToolRunRecord | None:
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(
                """
                select body from workflow_tool_runs
                where project_id=? and idempotency_key=? limit 1
                """,
                (project_id, idempotency_key),
            ).fetchone()
        return ToolRunRecord.model_validate_json(row[0]) if row is not None else None

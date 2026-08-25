"""Project-scoped execution run storage."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Protocol

from stem_sci.operators.models import OperatorRun


class ExecutionStore(Protocol):
    def put(self, run: OperatorRun) -> OperatorRun: ...

    def get(self, project_id: str, run_id: str) -> OperatorRun | None: ...

    def list_project(self, project_id: str) -> list[OperatorRun]: ...


class InMemoryExecutionStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], OperatorRun] = {}

    def put(self, run: OperatorRun) -> OperatorRun:
        self._items[(run.project_id, run.operator_run_id)] = run
        return run

    def get(self, project_id: str, run_id: str) -> OperatorRun | None:
        return self._items.get((project_id, run_id))

    def list_project(self, project_id: str) -> list[OperatorRun]:
        return [run for (run_project, _), run in self._items.items() if run_project == project_id]


class SQLiteExecutionStore:
    """SQLite-backed operator runs for project-scoped execution provenance."""

    def __init__(self, database: Path) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                create table if not exists workflow_execution_runs (
                    project_id text not null,
                    operator_run_id text not null,
                    body text not null,
                    primary key (project_id, operator_run_id)
                )
                """
            )

    def put(self, run: OperatorRun) -> OperatorRun:
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                insert into workflow_execution_runs(project_id, operator_run_id, body)
                values (?, ?, ?)
                on conflict(project_id, operator_run_id) do update set body=excluded.body
                """,
                (run.project_id, run.operator_run_id, run.model_dump_json()),
            )
        return run

    def get(self, project_id: str, run_id: str) -> OperatorRun | None:
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(
                "select body from workflow_execution_runs where project_id=? and operator_run_id=?",
                (project_id, run_id),
            ).fetchone()
        return OperatorRun.model_validate_json(row[0]) if row is not None else None

    def list_project(self, project_id: str) -> list[OperatorRun]:
        with sqlite3.connect(self.database) as connection:
            rows = connection.execute(
                """
                select body from workflow_execution_runs
                where project_id=? order by operator_run_id
                """,
                (project_id,),
            ).fetchall()
        return [OperatorRun.model_validate_json(row[0]) for row in rows]

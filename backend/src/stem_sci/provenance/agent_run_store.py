"""In-memory AgentRunRecord store used by the first Controller slice."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Protocol

from .models import AgentRunRecord


class AgentRunStore(Protocol):
    def put(self, record: AgentRunRecord) -> AgentRunRecord: ...

    def get(self, project_id: str, agent_run_id: str) -> AgentRunRecord | None: ...

    def list_project(self, project_id: str) -> list[AgentRunRecord]: ...


class InMemoryAgentRunStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], AgentRunRecord] = {}

    def put(self, record: AgentRunRecord) -> AgentRunRecord:
        self._items[(record.project_id, record.agent_run_id)] = record
        return record

    def get(self, project_id: str, agent_run_id: str) -> AgentRunRecord | None:
        return self._items.get((project_id, agent_run_id))

    def list_project(self, project_id: str) -> list[AgentRunRecord]:
        return [record for (record_project, _), record in self._items.items() if record_project == project_id]


class SQLiteAgentRunStore:
    """SQLite-backed Agent execution provenance."""

    def __init__(self, database: Path) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                create table if not exists workflow_agent_runs (
                    project_id text not null,
                    agent_run_id text not null,
                    body text not null,
                    primary key (project_id, agent_run_id)
                )
                """
            )

    def put(self, record: AgentRunRecord) -> AgentRunRecord:
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                insert into workflow_agent_runs(project_id, agent_run_id, body)
                values (?, ?, ?)
                on conflict(project_id, agent_run_id) do update set body=excluded.body
                """,
                (record.project_id, record.agent_run_id, record.model_dump_json()),
            )
        return record

    def get(self, project_id: str, agent_run_id: str) -> AgentRunRecord | None:
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(
                "select body from workflow_agent_runs where project_id=? and agent_run_id=?",
                (project_id, agent_run_id),
            ).fetchone()
        return AgentRunRecord.model_validate_json(row[0]) if row is not None else None

    def list_project(self, project_id: str) -> list[AgentRunRecord]:
        with sqlite3.connect(self.database) as connection:
            rows = connection.execute(
                """
                select body from workflow_agent_runs
                where project_id=? order by agent_run_id
                """,
                (project_id,),
            ).fetchall()
        return [AgentRunRecord.model_validate_json(row[0]) for row in rows]

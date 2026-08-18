"""Durable Controller snapshots for restart-safe project workflows."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class WorkflowSnapshot(BaseModel):
    """Serialized Controller state returned by a workflow store."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)
    project_intent: str = Field(min_length=1)
    workflow_state_json: str = Field(min_length=1)
    pending_approval_json: str | None = None


class WorkflowStore(Protocol):
    def save(
        self,
        project_id: str,
        project_intent: str,
        workflow_state: BaseModel,
        pending_approval: BaseModel | None,
    ) -> None: ...

    def get(self, project_id: str) -> WorkflowSnapshot | None: ...


class SQLiteWorkflowStore:
    """SQLite-backed snapshots; payloads remain versioned Pydantic JSON."""

    def __init__(self, database: Path) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                create table if not exists workflow_projects (
                    project_id text primary key,
                    project_intent text not null,
                    workflow_state_json text not null,
                    pending_approval_json text,
                    updated_at text not null default current_timestamp
                )
                """
            )

    def save(
        self,
        project_id: str,
        project_intent: str,
        workflow_state: BaseModel,
        pending_approval: BaseModel | None,
    ) -> None:
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                insert into workflow_projects(
                    project_id, project_intent, workflow_state_json, pending_approval_json, updated_at
                ) values (?, ?, ?, ?, current_timestamp)
                on conflict(project_id) do update set
                    project_intent=excluded.project_intent,
                    workflow_state_json=excluded.workflow_state_json,
                    pending_approval_json=excluded.pending_approval_json,
                    updated_at=current_timestamp
                """,
                (
                    project_id,
                    project_intent,
                    workflow_state.model_dump_json(),
                    pending_approval.model_dump_json() if pending_approval is not None else None,
                ),
            )

    def get(self, project_id: str) -> WorkflowSnapshot | None:
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(
                """
                select project_id, project_intent, workflow_state_json, pending_approval_json
                from workflow_projects where project_id=?
                """,
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        return WorkflowSnapshot(
            project_id=row[0],
            project_intent=row[1],
            workflow_state_json=row[2],
            pending_approval_json=row[3],
        )

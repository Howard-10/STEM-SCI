"""Durable user feedback records for conversational workflow control."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Protocol

from pydantic import Field

from stem_sci.core.models import DomainModel


class WorkflowFeedbackAction(str, Enum):
    CONTINUE = "continue"
    RERUN = "rerun"
    PAUSE = "pause"


class WorkflowFeedback(DomainModel):
    feedback_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    action: WorkflowFeedbackAction
    feedback: str = Field(min_length=1, max_length=10_000)
    created_by: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WorkflowFeedbackStore(Protocol):
    def put(self, feedback: WorkflowFeedback) -> WorkflowFeedback: ...

    def list_project(self, project_id: str) -> list[WorkflowFeedback]: ...


class InMemoryWorkflowFeedbackStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], WorkflowFeedback] = {}

    def put(self, feedback: WorkflowFeedback) -> WorkflowFeedback:
        self._items[(feedback.project_id, feedback.feedback_id)] = feedback
        return feedback

    def list_project(self, project_id: str) -> list[WorkflowFeedback]:
        return sorted(
            (item for (item_project_id, _), item in self._items.items() if item_project_id == project_id),
            key=lambda item: (item.created_at, item.feedback_id),
        )


class SQLiteWorkflowFeedbackStore:
    """SQLite-backed user feedback for project workflow timelines."""

    def __init__(self, database: Path) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                create table if not exists workflow_feedback (
                    project_id text not null,
                    feedback_id text not null,
                    created_at text not null,
                    body text not null,
                    primary key (project_id, feedback_id)
                )
                """
            )

    def put(self, feedback: WorkflowFeedback) -> WorkflowFeedback:
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                insert into workflow_feedback(project_id, feedback_id, created_at, body)
                values (?, ?, ?, ?)
                on conflict(project_id, feedback_id) do update set
                    created_at=excluded.created_at,
                    body=excluded.body
                """,
                (
                    feedback.project_id,
                    feedback.feedback_id,
                    feedback.created_at.isoformat(),
                    feedback.model_dump_json(),
                ),
            )
        return feedback

    def list_project(self, project_id: str) -> list[WorkflowFeedback]:
        with sqlite3.connect(self.database) as connection:
            rows = connection.execute(
                """
                select body from workflow_feedback
                where project_id=? order by created_at, feedback_id
                """,
                (project_id,),
            ).fetchall()
        return [WorkflowFeedback.model_validate_json(row[0]) for row in rows]

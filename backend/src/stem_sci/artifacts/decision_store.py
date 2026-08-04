"""Project-scoped human decision storage."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Protocol

from .models import ApprovalRecord


class DecisionStore(Protocol):
    def put(self, decision: ApprovalRecord) -> ApprovalRecord: ...

    def get(self, project_id: str, approval_id: str) -> ApprovalRecord | None: ...

    def get_by_idempotency(self, project_id: str, idempotency_key: str) -> ApprovalRecord | None: ...

    def list_project(self, project_id: str) -> list[ApprovalRecord]: ...


class InMemoryDecisionStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], ApprovalRecord] = {}
        self._idempotency: dict[tuple[str, str], str] = {}

    def put(self, decision: ApprovalRecord) -> ApprovalRecord:
        key = (decision.project_id, decision.approval_id)
        idempotency_key = (decision.project_id, decision.idempotency_key)
        existing_id = self._idempotency.get(idempotency_key)
        if existing_id is not None and existing_id != decision.approval_id:
            raise ValueError("idempotency key already belongs to another approval")
        self._items[key] = decision
        self._idempotency[idempotency_key] = decision.approval_id
        return decision

    def get(self, project_id: str, approval_id: str) -> ApprovalRecord | None:
        return self._items.get((project_id, approval_id))

    def get_by_idempotency(self, project_id: str, idempotency_key: str) -> ApprovalRecord | None:
        approval_id = self._idempotency.get((project_id, idempotency_key))
        return self.get(project_id, approval_id) if approval_id else None

    def list_project(self, project_id: str) -> list[ApprovalRecord]:
        return [item for (item_project, _), item in self._items.items() if item_project == project_id]


class SQLiteDecisionStore:
    """SQLite-backed project-scoped approvals with durable idempotency checks."""

    def __init__(self, database: Path) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                create table if not exists workflow_decisions (
                    project_id text not null,
                    approval_id text not null,
                    idempotency_key text not null,
                    body text not null,
                    primary key (project_id, approval_id),
                    unique (project_id, idempotency_key)
                )
                """
            )

    def put(self, decision: ApprovalRecord) -> ApprovalRecord:
        with sqlite3.connect(self.database) as connection:
            existing = connection.execute(
                "select approval_id from workflow_decisions where project_id=? and idempotency_key=?",
                (decision.project_id, decision.idempotency_key),
            ).fetchone()
            if existing is not None and existing[0] != decision.approval_id:
                raise ValueError("idempotency key already belongs to another approval")
            connection.execute(
                """
                insert into workflow_decisions(project_id, approval_id, idempotency_key, body)
                values (?, ?, ?, ?)
                on conflict(project_id, approval_id) do update set
                    idempotency_key=excluded.idempotency_key,
                    body=excluded.body
                """,
                (
                    decision.project_id,
                    decision.approval_id,
                    decision.idempotency_key,
                    decision.model_dump_json(),
                ),
            )
        return decision

    def get(self, project_id: str, approval_id: str) -> ApprovalRecord | None:
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(
                "select body from workflow_decisions where project_id=? and approval_id=?",
                (project_id, approval_id),
            ).fetchone()
        return ApprovalRecord.model_validate_json(row[0]) if row is not None else None

    def get_by_idempotency(self, project_id: str, idempotency_key: str) -> ApprovalRecord | None:
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(
                "select body from workflow_decisions where project_id=? and idempotency_key=?",
                (project_id, idempotency_key),
            ).fetchone()
        return ApprovalRecord.model_validate_json(row[0]) if row is not None else None

    def list_project(self, project_id: str) -> list[ApprovalRecord]:
        with sqlite3.connect(self.database) as connection:
            rows = connection.execute(
                "select body from workflow_decisions where project_id=? order by approval_id",
                (project_id,),
            ).fetchall()
        return [ApprovalRecord.model_validate_json(row[0]) for row in rows]

"""Durable route-decision history for Controller auditability."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Protocol

from .route_decision import RouteDecision


class RouteDecisionStore(Protocol):
    def put(self, decision: RouteDecision) -> RouteDecision: ...

    def get(self, project_id: str, decision_id: str) -> RouteDecision | None: ...

    def list_project(self, project_id: str) -> list[RouteDecision]: ...


class SQLiteRouteDecisionStore:
    """SQLite-backed route decisions ordered by their stable decision id."""

    def __init__(self, database: Path) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                create table if not exists workflow_route_decisions (
                    project_id text not null,
                    decision_id text not null,
                    body text not null,
                    primary key (project_id, decision_id)
                )
                """
            )

    def put(self, decision: RouteDecision) -> RouteDecision:
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                insert into workflow_route_decisions(project_id, decision_id, body)
                values (?, ?, ?)
                on conflict(project_id, decision_id) do update set body=excluded.body
                """,
                (decision.project_id, decision.decision_id, decision.model_dump_json()),
            )
        return decision

    def get(self, project_id: str, decision_id: str) -> RouteDecision | None:
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(
                "select body from workflow_route_decisions where project_id=? and decision_id=?",
                (project_id, decision_id),
            ).fetchone()
        return RouteDecision.model_validate_json(row[0]) if row is not None else None

    def list_project(self, project_id: str) -> list[RouteDecision]:
        with sqlite3.connect(self.database) as connection:
            rows = connection.execute(
                """
                select body from workflow_route_decisions
                where project_id=? order by decision_id
                """,
                (project_id,),
            ).fetchall()
        return [RouteDecision.model_validate_json(row[0]) for row in rows]

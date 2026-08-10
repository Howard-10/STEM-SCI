"""Project-isolated, auditable storage for human-approved decisions."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from stem_sci.compat.langgraph import BaseStore, InMemoryStore

if TYPE_CHECKING:
    from stem_sci.context.models import RuntimeContext


class DecisionStatus(StrEnum):
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"


class DecisionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    decision_id: str = Field(default_factory=lambda: f"dec_{uuid4().hex}")
    user_id: str
    project_id: str
    stage: str
    content: str = Field(min_length=1, max_length=12_000)
    decided_by: str
    source_artifact_refs: tuple[str, ...] = ()
    status: DecisionStatus = DecisionStatus.APPROVED
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class DecisionStore:
    def __init__(self, store: BaseStore | None = None) -> None:
        self.store = store or InMemoryStore()

    @staticmethod
    def _namespace(identity: RuntimeContext) -> tuple[str, ...]:
        return ("users", identity.user_id, "projects", identity.project_id, "decisions")

    def save(self, identity: RuntimeContext, decision: DecisionRecord) -> None:
        if decision.user_id != identity.user_id or decision.project_id != identity.project_id:
            raise ValueError("Decision identity does not match the active user/project scope")
        self.store.put(
            self._namespace(identity), decision.decision_id, decision.model_dump(mode="json")
        )

    def get(self, identity: RuntimeContext, decision_id: str) -> DecisionRecord:
        item = self.store.get(self._namespace(identity), decision_id)
        if item is None:
            raise KeyError("Decision not found in this user/project scope")
        return DecisionRecord.model_validate(item.value)

    def list_approved(self, identity: RuntimeContext) -> list[DecisionRecord]:
        decisions = [
            DecisionRecord.model_validate(item.value)
            for item in self.store.search(self._namespace(identity))
        ]
        return [decision for decision in decisions if decision.status is DecisionStatus.APPROVED]

    def supersede(
        self, identity: RuntimeContext, decision_id: str, replacement: DecisionRecord
    ) -> None:
        current = self.get(identity, decision_id)
        if replacement.user_id != current.user_id or replacement.project_id != current.project_id:
            raise ValueError("Replacement decision must remain in the same project scope")
        superseded = current.model_copy(
            update={
                "status": DecisionStatus.SUPERSEDED,
                "updated_at": datetime.now(UTC),
            }
        )
        self.save(identity, superseded)
        self.save(identity, replacement)

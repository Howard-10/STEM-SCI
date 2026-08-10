"""Typed contracts for conservative, user-controlled memory."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class MemoryScope(StrEnum):
    USER = "user"
    PROJECT = "project"


class MemoryKind(StrEnum):
    USER_PREFERENCE = "user_preference"
    APPROVED_DECISION = "approved_decision"
    PROJECT_CONSTRAINT = "project_constraint"
    STAGE_SUMMARY = "stage_summary"
    UNRESOLVED_ISSUE = "unresolved_issue"


class MemoryStatus(StrEnum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"
    DELETED = "deleted"


class Sensitivity(StrEnum):
    NORMAL = "normal"
    SENSITIVE = "sensitive"
    PROHIBITED = "prohibited"


class MemoryCandidate(BaseModel):
    """Unsaved proposal that requires an explicit confirmation call."""

    model_config = ConfigDict(frozen=True)
    memory_id: str = Field(default_factory=lambda: f"mem_{uuid4().hex}")
    scope: MemoryScope
    kind: MemoryKind
    content: str = Field(min_length=1, max_length=4_000)
    source_message_ids: tuple[str, ...] = ()
    sensitivity: Sensitivity = Sensitivity.NORMAL
    rationale: str = "explicitly stated"
    status: MemoryStatus = MemoryStatus.CANDIDATE


class MemoryCandidateBatch(BaseModel):
    candidates: list[MemoryCandidate] = Field(default_factory=list, max_length=20)


class MemoryRecord(BaseModel):
    """Confirmed memory stored under an isolated user/project namespace."""

    model_config = ConfigDict(frozen=True)
    memory_id: str
    user_id: str
    project_id: str | None = None
    scope: MemoryScope
    kind: MemoryKind
    content: str = Field(min_length=1, max_length=4_000)
    source_message_ids: tuple[str, ...] = ()
    status: MemoryStatus = MemoryStatus.CONFIRMED
    sensitivity: Sensitivity = Sensitivity.NORMAL
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationSummary(BaseModel):
    """Loss-aware summary of messages removed from the active context."""

    user_goals: tuple[str, ...] = ()
    approved_decisions: tuple[str, ...] = ()
    unresolved_issues: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    failure_reasons: tuple[str, ...] = ()
    process_summary: str = ""
    summarized_message_ids: tuple[str, ...] = ()
    created_at: datetime = Field(default_factory=utc_now)

    def as_context(self) -> str:
        sections = []
        for title, values in (
            ("User goals", self.user_goals),
            ("Approved decisions", self.approved_decisions),
            ("Unresolved issues", self.unresolved_issues),
            ("Evidence references", self.evidence_refs),
            ("Failure reasons", self.failure_reasons),
        ):
            if values:
                sections.append(f"{title}: " + "; ".join(values))
        if self.process_summary:
            sections.append("Process summary: " + self.process_summary)
        return "\n".join(sections)

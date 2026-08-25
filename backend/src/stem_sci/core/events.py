"""Structured workflow risk and error events."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from .models import DomainModel


class EventType(StrEnum):
    RISK_FLAGGED = "RISK_FLAGGED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    ROUTED = "ROUTED"
    EXECUTION_BLOCKED = "EXECUTION_BLOCKED"
    REWORK_REQUESTED = "REWORK_REQUESTED"


class ResearchEvent(DomainModel):
    event_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    event_type: EventType
    subject_ref: str = Field(min_length=1)
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: datetime

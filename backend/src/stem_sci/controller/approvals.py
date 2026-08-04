"""Approval interrupt contracts shared by Controller adapters."""

from __future__ import annotations

from pydantic import Field

from stem_sci.core.models import DomainModel


class ApprovalInterrupt(DomainModel):
    request_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    reason: str = Field(min_length=1)


def approval_idempotency_key(interrupt: ApprovalInterrupt, decision: str) -> str:
    if not decision:
        raise ValueError("decision must not be empty")
    return f"resume:{interrupt.request_id}:{decision}"

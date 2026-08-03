"""Atomic, single-type scientific claim contracts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ClaimType(StrEnum):
    LITERATURE = "LITERATURE"
    RESULT = "RESULT"
    METHOD = "METHOD"
    INTERPRETATION = "INTERPRETATION"
    SPECULATION = "SPECULATION"
    LIMITATION = "LIMITATION"


class AtomicClaim(BaseModel):
    """One claim with exactly one type and explicit evidence references."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    claim_type: ClaimType
    evidence_refs: list[str] = Field(default_factory=list)
    result_card_ref: str | None = None
    human_approval_ref: str | None = None

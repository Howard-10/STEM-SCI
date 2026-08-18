"""Reference-only domain models shared by workflow components."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .enums import DecisionScope, GateDecision


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArtifactRef(DomainModel):
    """A pointer to a versioned artifact; content stays outside ResearchState."""

    artifact_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    version: int = Field(ge=1)
    content_uri: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)
    created_at: datetime
    created_by: str = Field(min_length=1)
    status: str = "CANDIDATE"
    supersedes_ref: str | None = None


class ApprovalRecord(DomainModel):
    approval_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    artifact_version: int = Field(ge=1)
    decision: str = Field(min_length=1)
    decided_by: str = Field(min_length=1)
    decided_at: datetime
    reason: str | None = None
    risk_acknowledgements: list[str] = Field(default_factory=list)
    previous_approval_ref: str | None = None
    idempotency_key: str = Field(min_length=1)


class GateResult(DomainModel):
    gate_id: str = Field(min_length=1)
    gate_version: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    decision: GateDecision
    decision_scope: DecisionScope
    blocked_target_ids: list[str] = Field(default_factory=list)
    research_test_result_refs: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    next_action: str = Field(min_length=1)
    created_at: datetime

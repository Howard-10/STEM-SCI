"""Versioned contracts for tools invoked through the Controller gateway."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, JsonValue

from stem_sci.context.models import StrictModel


class ToolExecutionMode(StrEnum):
    """The Controller-enforced write boundary for a tool."""

    READ_ONLY = "READ_ONLY"
    CANDIDATE_OUTPUT = "CANDIDATE_OUTPUT"
    CONTROLLED_WRITE = "CONTROLLED_WRITE"


class ToolRunStatus(StrEnum):
    """Lifecycle state of one Controller-mediated tool run."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


class ToolSpec(StrictModel):
    """Declarative capability and policy contract for a registered tool."""

    tool_id: str = Field(min_length=1)
    tool_version: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    execution_mode: ToolExecutionMode
    input_schema_ref: str = Field(min_length=1)
    output_schema_ref: str = Field(min_length=1)
    required_permissions: list[str] = Field(default_factory=list)
    project_scope_required: bool = True
    network_policy: Literal["disabled", "allowlisted"] = "disabled"
    sandbox_profile: str | None = None
    timeout_seconds: int = Field(gt=0)
    retry_policy: dict[str, int] = Field(default_factory=dict)
    estimated_cost: float = Field(default=0.0, ge=0.0)
    idempotency_policy: Literal["required", "optional", "none"] = "required"


class ToolResult(StrictModel):
    """Outcome returned by a tool executor; policy blocks are represented here."""

    tool_run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    tool_id: str = Field(min_length=1)
    tool_version: str = Field(min_length=1)
    status: ToolRunStatus
    output_artifact_refs: list[str] = Field(default_factory=list)
    output_content_refs: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    error_code: str | None = None
    # Optional structured payloads supplied by local Tool implementations.
    # The Gateway is the only component that persists these as candidate content.
    output_payloads: list[dict[str, JsonValue]] = Field(
        default_factory=list, exclude=True, repr=False
    )


class CandidateOutputPayload(StrictModel):
    """Transient candidate content accepted only by the Controller Gateway."""

    project_id: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    artifact_type: str = Field(min_length=1)
    schema_ref: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    body: dict[str, JsonValue]
    content_hash: str = Field(min_length=64, max_length=64)


class ToolRunRecord(StrictModel):
    """Allowlisted audit projection for one Controller-mediated Tool run."""

    tool_run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    tool_id: str = Field(min_length=1)
    tool_version: str = Field(min_length=1)
    status: ToolRunStatus
    output_artifact_refs: list[str] = Field(default_factory=list)
    output_content_refs: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    error_code: str | None = None

    agent_id: str = Field(min_length=1)
    agent_run_id: str = Field(min_length=1)
    skill_ref: str = Field(min_length=1)
    request_ref: str = Field(min_length=1)
    idempotency_key: str | None = None
    operation_hash: str | None = None
    input_artifact_refs: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None

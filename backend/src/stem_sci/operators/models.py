"""Deterministic operator contracts; implementations are intentionally replaceable."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from stem_sci.core.enums import RunStatus
from stem_sci.core.models import DomainModel


class OperatorSpec(DomainModel):
    operator_id: str = Field(min_length=1)
    operator_version: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    input_schema_ref: str = Field(min_length=1)
    output_schema_ref: str = Field(min_length=1)
    required_permissions: list[str] = Field(default_factory=list)
    supported_artifact_types: list[str] = Field(default_factory=list)
    estimated_cost: float | None = None
    timeout_seconds: int = Field(gt=0)
    retry_policy: dict[str, int] = Field(default_factory=dict)
    health_check_required: bool = True


class OperatorRun(DomainModel):
    operator_run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    operator_version: str = Field(min_length=1)
    request_ref: str = Field(min_length=1)
    input_artifact_refs: list[str] = Field(default_factory=list)
    output_artifact_refs: list[str] = Field(default_factory=list)
    environment_ref: str | None = None
    log_ref: str | None = None
    error_ref: str | None = None
    status: RunStatus = RunStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None

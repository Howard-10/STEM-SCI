"""Reference-only project state owned by the Controller."""

from __future__ import annotations

from pydantic import Field

from .enums import ProjectStage, TaskStatus
from .models import DomainModel


class ResearchState(DomainModel):
    """Small project ledger; large payloads must remain in stores."""

    project_id: str = Field(min_length=1)
    current_stage: ProjectStage = ProjectStage.INTAKE
    rework_target_agent: str | None = None
    rework_target_refs: list[str] = Field(default_factory=list)
    rework_reason: str | None = None
    rework_trigger_refs: list[str] = Field(default_factory=list)
    task_status: dict[str, TaskStatus] = Field(default_factory=dict)
    task_ledger: list[str] = Field(default_factory=list)
    progress_ledger: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    context_bundle_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    data_asset_refs: list[str] = Field(default_factory=list)
    execution_run_refs: list[str] = Field(default_factory=list)
    protocol_refs: list[str] = Field(default_factory=list)
    research_test_result_refs: list[str] = Field(default_factory=list)
    risk_profile_refs: list[str] = Field(default_factory=list)
    route_decision_refs: list[str] = Field(default_factory=list)
    agent_run_refs: list[str] = Field(default_factory=list)
    approval_request_refs: list[str] = Field(default_factory=list)
    budget_state_ref: str | None = None
    recent_rounds: list[str] = Field(default_factory=list)
    short_memory_summary: str | None = None
    long_memory_refs: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    error_log: list[str] = Field(default_factory=list)

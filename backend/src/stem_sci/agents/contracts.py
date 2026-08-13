"""Structured contracts shared by the six domain agents.

The contracts deliberately describe *proposals*.  A result returned by an
agent is not an approval, a workflow transition, a dataset freeze, or an
official statistical result.  Those operations belong to the Controller and
deterministic operators in later phases.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from stem_sci.core.enums import DecisionScope


class AgentContract(BaseModel):
    """Base model for protocol objects crossing an agent boundary."""

    model_config = ConfigDict(extra="forbid")


class AgentInput(AgentContract):
    """References and capabilities supplied by the Controller for one run."""

    agent_run_id: str = Field(min_length=1)
    task_ref: str = Field(min_length=1)
    context_bundle_ref: str = Field(min_length=1)
    allowed_tool_capabilities: list[str] = Field(default_factory=list)
    allowed_output_types: list[str] = Field(default_factory=list)
    policy_version: str = Field(min_length=1)
    prompt_template_version: str = Field(min_length=1)


class ToolRequest(AgentContract):
    """A request for a deterministic operator; it is not an execution command."""

    request_id: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    input_refs: list[str] = Field(default_factory=list)
    required_output_types: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)


class CandidateArtifact(AgentContract):
    """Transient structured content that only the Controller may persist."""

    candidate_ref: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    body: dict[str, JsonValue]


class AgentResult(AgentContract):
    """Candidate outputs from an agent; governance fields are intentionally absent."""

    agent_run_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    agent_version: str = Field(min_length=1)
    candidate_artifact_refs: list[str] = Field(default_factory=list)
    # Candidate content is transient until the Controller persists it, but it
    # must remain serializable so an orchestrator can validate and store it.
    candidate_artifacts: list[CandidateArtifact] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    llm_metadata_refs: list[str] = Field(default_factory=list)
    tool_requests: list[ToolRequest] = Field(default_factory=list)
    approval_requests: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    created_at: datetime


class AgentCapability(AgentContract):
    """Machine-readable role boundary advertised to the Controller."""

    agent_id: str = Field(min_length=1)
    supported_task_types: list[str] = Field(default_factory=list)
    allowed_tool_capabilities: list[str] = Field(default_factory=list)
    allowed_output_types: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    read_only_global_state: bool = True


class ApprovalRequest(AgentContract):
    """A request that the Controller route to a human approval node."""

    request_id: str = Field(min_length=1)
    artifact_ref: str = Field(min_length=1)
    approval_type: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    risk_summary: str = Field(min_length=1)


class ReviewFinding(AgentContract):
    """One independent-review finding; it never mutates the reviewed artifact."""

    finding_id: str = Field(min_length=1)
    reviewer_type: str = Field(min_length=1)
    artifact_ref: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    category: str = Field(min_length=1)
    description: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    suggested_action: str = Field(min_length=1)
    decision_scope: DecisionScope = DecisionScope.ARTIFACT
    blocked_target_ids: list[str] = Field(default_factory=list)


class RevisionRequest(AgentContract):
    """A read-only request describing changes that a Controller may route."""

    revision_id: str = Field(min_length=1)
    artifact_ref: str = Field(min_length=1)
    required_changes: list[str] = Field(min_length=1)
    blocking: bool = False
    triggered_by_refs: list[str] = Field(default_factory=list)


class ReviewReport(AgentContract):
    """Aggregate reviewer output, without approval or release authority."""

    review_report_id: str = Field(min_length=1)
    finding_refs: list[str] = Field(default_factory=list)
    revision_request_refs: list[str] = Field(default_factory=list)
    overall_recommendation: Literal["PASS", "MINOR_REVISION", "MAJOR_REVISION", "BLOCK"]

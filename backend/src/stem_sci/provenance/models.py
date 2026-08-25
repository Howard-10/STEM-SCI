"""Cross-domain provenance records for Agent and Operator runs."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from stem_sci.core.models import DomainModel


class AgentRunRecord(DomainModel):
    agent_run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    agent_version: str = Field(min_length=1)
    prompt_template_version: str = Field(min_length=1)
    input_artifact_refs: list[str] = Field(default_factory=list)
    output_artifact_refs: list[str] = Field(default_factory=list)
    tool_run_refs: list[str] = Field(default_factory=list)
    llm_metadata_refs: list[str] = Field(default_factory=list)
    reviewer_feedback_refs: list[str] = Field(default_factory=list)
    route_decision_ref: str | None = None
    started_at: datetime
    finished_at: datetime | None = None

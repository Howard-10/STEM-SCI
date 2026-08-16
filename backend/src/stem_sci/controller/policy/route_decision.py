"""Auditable route decisions emitted by the Controller."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from stem_sci.core.enums import DecisionScope, ProjectStage
from stem_sci.core.models import DomainModel


class RouteDecision(DomainModel):
    decision_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    current_stage: ProjectStage
    selected_route: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    required_context: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    decision_scope: DecisionScope
    blocked_target_ids: list[str] = Field(default_factory=list)
    risk_level: str = "LOW"
    triggered_rules: list[str] = Field(default_factory=list)
    final_decider: str = "controller"
    policy_version: str = "controller-policy-v1"
    created_at: datetime

"""Small explainable risk engine used before dynamic scoring is introduced."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from stem_sci.agents.contracts import AgentResult
from stem_sci.core.models import DomainModel


class RiskProfile(DomainModel):
    risk_profile_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    levels: dict[str, str] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    created_at: datetime


class RiskEngine:
    def assess_agent_result(self, project_id: str, result: AgentResult) -> RiskProfile:
        levels = {flag: "HIGH" for flag in result.risk_flags}
        rationale = list(result.unresolved_questions)
        if not result.candidate_artifact_refs:
            levels["MISSING_CANDIDATE"] = "HIGH"
            rationale.append("Agent returned no candidate artifact reference.")
        return RiskProfile(
            risk_profile_id=f"risk-{result.agent_run_id}",
            project_id=project_id,
            levels=levels,
            flags=list(levels),
            rationale=rationale,
            created_at=datetime.now(UTC),
        )

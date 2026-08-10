"""Read-only reproducibility-review contracts for manuscript numeric claims."""

from __future__ import annotations

from pydantic import Field

from typing import Literal

from stem_sci.agents.contracts import AgentContract, ReviewFinding, ReviewReport, RevisionRequest
from stem_sci.core.enums import DecisionScope
from stem_sci.statistics.models import StatisticalResultCard


class ManuscriptNumericClaim(AgentContract):
    """One number quoted by a manuscript, with its intended result-card link."""

    claim_ref: str = Field(min_length=1)
    result_card_ref: str = Field(min_length=1)
    result_key: str = Field(min_length=1)
    reported_value: float


class ReproducibilityReviewInput(AgentContract):
    """Controller-supplied, read-only material for a numeric consistency check."""

    project_id: str = Field(min_length=1)
    manuscript_ref: str = Field(min_length=1)
    numeric_claims: list[ManuscriptNumericClaim] = Field(min_length=1)
    statistical_result_cards: list[StatisticalResultCard] = Field(min_length=1)
    tolerance: float = Field(ge=0.0, default=1e-9)


class ReproducibilityReviewOutcome(AgentContract):
    """Only review artifacts; no paper, result, data, or state mutation."""

    findings: list[ReviewFinding] = Field(default_factory=list)
    revision_requests: list[RevisionRequest] = Field(default_factory=list)
    report: ReviewReport


class CitationReviewItem(AgentContract):
    claim_ref: str = Field(min_length=1)
    evidence_ref: str = Field(min_length=1)
    source_chunk_ref: str | None = None
    verification_status: Literal[
        "demo_seed", "model_generated_unverified", "source_verified", "human_verified"
    ]
    supports_claim: bool
    context_adequate: bool


class CitationReviewInput(AgentContract):
    project_id: str = Field(min_length=1)
    manuscript_ref: str = Field(min_length=1)
    citations: list[CitationReviewItem] = Field(min_length=1)


class ReviewCriterion(AgentContract):
    criterion_id: str = Field(min_length=1)
    artifact_ref: str = Field(min_length=1)
    category: str = Field(min_length=1)
    description: str = Field(min_length=1)
    passed: bool
    evidence_refs: list[str] = Field(default_factory=list)
    severity: Literal["minor", "major", "critical"] = "major"
    decision_scope: DecisionScope = DecisionScope.ARTIFACT
    blocked_target_ids: list[str] = Field(default_factory=list)


class MethodReviewInput(AgentContract):
    project_id: str = Field(min_length=1)
    protocol_ref: str = Field(min_length=1)
    criteria: list[ReviewCriterion] = Field(min_length=1)


class PedagogyReviewInput(AgentContract):
    project_id: str = Field(min_length=1)
    study_protocol_ref: str = Field(min_length=1)
    criteria: list[ReviewCriterion] = Field(min_length=1)


class GeneralReviewOutcome(AgentContract):
    findings: list[ReviewFinding] = Field(default_factory=list)
    revision_requests: list[RevisionRequest] = Field(default_factory=list)
    report: ReviewReport


class ReviewArbiterInput(AgentContract):
    project_id: str = Field(min_length=1)
    reviewed_artifact_ref: str = Field(min_length=1)
    findings: list[ReviewFinding] = Field(default_factory=list)


class ReviewArbiterOutcome(AgentContract):
    report: ReviewReport

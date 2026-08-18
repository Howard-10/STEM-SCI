"""Read-only reproducibility-review contracts for manuscript numeric claims."""

from __future__ import annotations

from pydantic import Field, model_validator

from typing import Literal

from stem_sci.agents.contracts import AgentContract, ReviewFinding, ReviewReport, RevisionRequest
from stem_sci.agents.writing_pipeline.models import AtomicClaimGraph
from stem_sci.context.models import EvidenceRef
from stem_sci.core.enums import DecisionScope
from stem_sci.statistics.models import StatisticalResultCard
from stem_sci.coding.models import CodeArtifact, CodeSpecification
from stem_sci.coding.review import CodeReviewResult
from stem_sci.research_data.models import AnalysisDatasetRef
from stem_sci.statistics.models import ReproducibilityManifest, ResultValidationReport
from stem_sci.operators.models import OperatorRun


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

    @model_validator(mode="after")
    def require_project_scoped_result_cards(self) -> "ReproducibilityReviewInput":
        if any(card.project_id != self.project_id for card in self.statistical_result_cards):
            raise ValueError("review input may not contain another project's StatisticalResultCard")
        return self


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


class ManuscriptTraceabilityReviewInput(AgentContract):
    """Read-only objects required for deterministic claim-traceability review."""

    project_id: str = Field(min_length=1)
    manuscript_ref: str = Field(min_length=1)
    claim_graph: AtomicClaimGraph
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    approved_study_protocol_refs: list[str] = Field(default_factory=list)
    validated_result_cards: list[StatisticalResultCard] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_project_scoped_material(self) -> "ManuscriptTraceabilityReviewInput":
        if self.claim_graph.project_id != self.project_id:
            raise ValueError("claim graph project does not match review project")
        if any(item.project_id != self.project_id for item in self.evidence_refs):
            raise ValueError("review input may not contain another project's evidence")
        if any(card.project_id != self.project_id for card in self.validated_result_cards):
            raise ValueError("review input may not contain another project's StatisticalResultCard")
        return self


class ReviewPacket(AgentContract):
    """Controller-whitelisted immutable traceability material for independent review.

    It deliberately carries hashes and artifact references, never row-level
    datasets, analysis-agent hidden reasoning, or any write-capable service.
    """

    project_id: str = Field(min_length=1)
    study_protocol_ref: str = Field(min_length=1)
    preregistered_plan_ref: str = Field(min_length=1)
    code_specification: CodeSpecification
    code_artifact: CodeArtifact
    code_review_result: CodeReviewResult
    analysis_dataset: AnalysisDatasetRef
    execution_run: OperatorRun
    validation_report: ResultValidationReport
    reproducibility_manifest: ReproducibilityManifest
    statistical_result_cards: list[StatisticalResultCard] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_project_scoped_immutable_artifacts(self) -> "ReviewPacket":
        project_scoped = [
            self.code_artifact.project_id,
            self.code_review_result.project_id,
            self.analysis_dataset.project_id,
            self.execution_run.project_id,
            self.validation_report.project_id,
            self.reproducibility_manifest.project_id,
            *(card.project_id for card in self.statistical_result_cards),
        ]
        if any(project_id != self.project_id for project_id in project_scoped):
            raise ValueError("review packet may not contain another project's artifacts")
        return self


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

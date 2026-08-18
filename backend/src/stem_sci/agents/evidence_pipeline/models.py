"""Typed contracts for bounded-corpus evidence synthesis."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from stem_sci.context.models import EvidenceRef, VerificationStatus


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PackageStatus(StrEnum):
    READY = "READY"
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class ScreeningStatus(StrEnum):
    INCLUDE = "INCLUDE"
    EXCLUDE = "EXCLUDE"
    UNCERTAIN = "UNCERTAIN"


class EvidenceReviewContext(EvidenceModel):
    project_id: str = Field(min_length=1)
    context_bundle_ref: str = Field(min_length=1)
    research_scope: str = Field(min_length=1)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    inclusion_criteria: list[str] = Field(default_factory=list)
    exclusion_criteria: list[str] = Field(default_factory=list)
    corpus_time_boundary: str | None = None
    intended_use: Literal["formal", "demo"] = "formal"
    context_hash: str = Field(min_length=64, max_length=64)
    allowed_verification_statuses: list[VerificationStatus] = Field(
        default_factory=lambda: [
            VerificationStatus.SOURCE_VERIFIED,
            VerificationStatus.HUMAN_VERIFIED,
            VerificationStatus.DEMO_SEED,
        ]
    )


class CorpusCoverageReport(EvidenceModel):
    report_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    source_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    covered_topics: list[str] = Field(default_factory=list)
    missing_topics: list[str] = Field(default_factory=list)


class ScreeningDecision(EvidenceModel):
    source_ref: str = Field(min_length=1)
    decision: ScreeningStatus
    reason: str = Field(min_length=1)
    criteria_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class PaperCard(EvidenceModel):
    paper_card_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    title: str = Field(min_length=1)
    research_question: str | None = None
    population: str | None = None
    context: str | None = None
    design: str | None = None
    sample: str | None = None
    intervention: str | None = None
    outcomes: list[str] = Field(default_factory=list)
    main_findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(min_length=1)


class EvidenceMatrixRow(EvidenceModel):
    row_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    research_question: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    relation: str = Field(pattern="^(SUPPORTING|CONTRASTING|MENTIONING)$")
    finding: str = Field(min_length=1)
    applicability_boundary: str | None = None
    evidence_refs: list[str] = Field(min_length=1)


class EvidenceConflict(EvidenceModel):
    conflict_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    supporting_evidence_refs: list[str] = Field(default_factory=list)
    contrasting_evidence_refs: list[str] = Field(default_factory=list)


class EvidenceConflictMap(EvidenceModel):
    map_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    conflicts: list[EvidenceConflict] = Field(default_factory=list)


class ResearchGap(EvidenceModel):
    gap_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)


class ResearchGapReport(EvidenceModel):
    report_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    gaps: list[ResearchGap] = Field(default_factory=list)
    limit_text: str = Field(min_length=1)


class BoundedEvidenceSynthesis(EvidenceModel):
    synthesis_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    evidence_refs: list[str] = Field(min_length=1)
    corpus_limit: str = Field(min_length=1)


class EvidenceSufficiencyReport(EvidenceModel):
    report_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    status: PackageStatus
    evidence_count: int = Field(ge=0)
    missing_requirements: list[str] = Field(default_factory=list)


class EvidenceReviewPackage(EvidenceModel):
    project_id: str = Field(min_length=1)
    status: PackageStatus
    coverage_report: CorpusCoverageReport | None = None
    screening_decisions: list[ScreeningDecision] = Field(default_factory=list)
    paper_cards: list[PaperCard] = Field(default_factory=list)
    evidence_matrix: list[EvidenceMatrixRow] = Field(default_factory=list)
    conflict_map: EvidenceConflictMap | None = None
    research_gap_report: ResearchGapReport | None = None
    synthesis: BoundedEvidenceSynthesis | None = None
    sufficiency: EvidenceSufficiencyReport
    used_evidence_refs: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    generation_metadata_refs: list[str] = Field(default_factory=list)


class PaperCardBatch(EvidenceModel):
    cards: list[PaperCard] = Field(default_factory=list)


class EvidenceMatrixBatch(EvidenceModel):
    rows: list[EvidenceMatrixRow] = Field(default_factory=list)


class ConflictGapResponse(EvidenceModel):
    conflict_map: EvidenceConflictMap
    gap_report: ResearchGapReport


class SynthesisResponse(EvidenceModel):
    synthesis: BoundedEvidenceSynthesis

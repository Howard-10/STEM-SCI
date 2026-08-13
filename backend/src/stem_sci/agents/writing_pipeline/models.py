"""Typed contracts for claim-safe bilingual manuscript drafting."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from stem_sci.agents.evidence_pipeline import PaperCard
from stem_sci.context.models import EvidenceRef
from stem_sci.core.claims import ClaimType


class WritingModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClaimRelation(StrEnum):
    SUPPORTS = "SUPPORTS"
    INTERPRETS = "INTERPRETS"
    QUALIFIES = "QUALIFIES"
    LIMITS = "LIMITS"
    CONTRADICTS = "CONTRADICTS"
    DERIVED_FROM = "DERIVED_FROM"


class LanguageCode(StrEnum):
    ZH_CN = "zh-CN"
    EN_US = "en-US"


class BilingualConsistencyStatus(StrEnum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"


class WritingSufficiencyStatus(StrEnum):
    READY = "READY"
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"


class AtomicClaimNode(WritingModel):
    project_id: str = Field(min_length=1)
    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    claim_type: ClaimType
    evidence_refs: list[str] = Field(default_factory=list)
    result_card_ref: str | None = None
    method_ref: str | None = None
    interpretation_boundary_ref: str | None = None
    human_approval_ref: str | None = None
    relations: list[tuple[str, ClaimRelation]] = Field(default_factory=list)
    section_target: str = Field(min_length=1)
    strength: str = "bounded"


class AtomicClaimGraph(WritingModel):
    project_id: str = Field(min_length=1)
    nodes: list[AtomicClaimNode] = Field(default_factory=list)
    graph_hash: str | None = Field(default=None, min_length=64, max_length=64)

    @property
    def result_claims(self) -> list[AtomicClaimNode]:
        return [node for node in self.nodes if node.claim_type is ClaimType.RESULT]


class WritingContextBundle(WritingModel):
    project_id: str = Field(min_length=1)
    approved_research_scope: str = Field(min_length=1)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    paper_cards: list[PaperCard] = Field(default_factory=list)
    evidence_matrix: list[dict[str, object]] = Field(default_factory=list)
    approved_study_protocol_refs: list[str] = Field(default_factory=list)
    validated_result_cards: list[str] = Field(default_factory=list)
    interpretation_boundaries: list[str] = Field(default_factory=list)
    prior_review_findings: list[str] = Field(default_factory=list)
    intended_use: Literal["formal", "demo"] = "formal"
    output_language: LanguageCode = LanguageCode.ZH_CN
    context_hash: str = Field(min_length=64, max_length=64)


class ManuscriptOutline(WritingModel):
    outline_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    section_claim_ids: dict[str, list[str]] = Field(default_factory=dict)


class ManuscriptDraft(WritingModel):
    project_id: str = Field(min_length=1)
    language: LanguageCode
    sections: dict[str, str] = Field(default_factory=dict)
    claim_ids: list[str] = Field(default_factory=list)
    citation_refs: list[str] = Field(default_factory=list)
    numeric_literals: list[str] = Field(default_factory=list)
    result_directions: dict[str, str] = Field(default_factory=dict)
    claim_strengths: dict[str, str] = Field(default_factory=dict)
    limitation_claim_ids: list[str] = Field(default_factory=list)
    status: str = Field(min_length=1)


class BilingualConsistencyReport(WritingModel):
    report_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    status: BilingualConsistencyStatus
    risk_flags: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)


class WritingSufficiencyReport(WritingModel):
    report_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    status: WritingSufficiencyStatus
    missing_requirements: list[str] = Field(default_factory=list)


class WritingPackage(WritingModel):
    project_id: str = Field(min_length=1)
    claim_graph: AtomicClaimGraph
    outline: ManuscriptOutline | None = None
    chinese: ManuscriptDraft
    english: ManuscriptDraft
    consistency: BilingualConsistencyReport
    sufficiency: WritingSufficiencyReport
    risk_flags: list[str] = Field(default_factory=list)
    generation_metadata_refs: list[str] = Field(default_factory=list)


class ClaimGraphResponse(WritingModel):
    graph: AtomicClaimGraph


class OutlineResponse(WritingModel):
    outline: ManuscriptOutline


class DraftResponse(WritingModel):
    draft: ManuscriptDraft

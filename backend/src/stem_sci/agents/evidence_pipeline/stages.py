"""Deterministic and structured-generation stages for evidence review."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Generic, TypeVar

from stem_sci.agents.runtime import GenerationResult, PromptRegistry, StructuredGenerator

from .models import (
    BoundedEvidenceSynthesis,
    ConflictGapResponse,
    CorpusCoverageReport,
    EvidenceConflictMap,
    EvidenceMatrixBatch,
    EvidenceMatrixRow,
    EvidenceReviewContext,
    PaperCard,
    PaperCardBatch,
    ResearchGapReport,
    ScreeningDecision,
    ScreeningStatus,
    SynthesisResponse,
)

T = TypeVar("T")


@dataclass(frozen=True)
class StageOutput(Generic[T]):
    value: T
    metadata_ref: str


def audit_corpus(context: EvidenceReviewContext) -> CorpusCoverageReport:
    return CorpusCoverageReport(
        report_id=f"coverage-{context.project_id}",
        project_id=context.project_id,
        source_count=len(set(context.source_refs)),
        evidence_count=len(context.evidence_refs),
        covered_topics=[context.research_scope] if context.evidence_refs else [],
        missing_topics=[] if context.evidence_refs else [context.research_scope],
    )


def screen_sources(
    context: EvidenceReviewContext, report: CorpusCoverageReport
) -> list[ScreeningDecision]:
    del report
    decisions: list[ScreeningDecision] = []
    for source_ref in sorted(set(context.source_refs)):
        evidence_ids = [
            evidence.evidence_id
            for evidence in context.evidence_refs
            if evidence.source_id == source_ref
        ]
        decisions.append(
            ScreeningDecision(
                source_ref=source_ref,
                decision=(ScreeningStatus.INCLUDE if evidence_ids else ScreeningStatus.UNCERTAIN),
                reason=(
                    "Verified project evidence is available."
                    if evidence_ids
                    else "No verified project evidence is available."
                ),
                evidence_refs=evidence_ids,
            )
        )
    return decisions


def extract_paper_cards(
    context: EvidenceReviewContext,
    included: list[ScreeningDecision],
    generator: StructuredGenerator,
    registry: PromptRegistry,
    model: str,
) -> StageOutput[list[PaperCard]]:
    included_sources = {
        decision.source_ref
        for decision in included
        if decision.decision is ScreeningStatus.INCLUDE
    }
    payload = {
        "project_id": context.project_id,
        "research_scope": context.research_scope,
        "evidence": [
            evidence.model_dump(mode="json")
            for evidence in context.evidence_refs
            if evidence.source_id in included_sources
        ],
    }
    system, user = registry.render(
        "paper_cards", "evidence-review-v1", payload=_json(payload)
    )
    result = generator.generate(
        system_prompt=system,
        user_prompt=user,
        response_model=PaperCardBatch,
        model=model,
        prompt_version="evidence-review-v1",
    )
    parsed = result.parsed_output
    assert isinstance(parsed, PaperCardBatch)
    return StageOutput(parsed.cards, _metadata_ref(context.project_id, result))


def build_evidence_matrix(
    context: EvidenceReviewContext,
    cards: list[PaperCard],
    generator: StructuredGenerator,
    registry: PromptRegistry,
    model: str,
) -> StageOutput[list[EvidenceMatrixRow]]:
    system, user = registry.render(
        "evidence_matrix",
        "evidence-review-v1",
        payload=_json([card.model_dump(mode="json") for card in cards]),
    )
    result = generator.generate(
        system_prompt=system,
        user_prompt=user,
        response_model=EvidenceMatrixBatch,
        model=model,
        prompt_version="evidence-review-v1",
    )
    parsed = result.parsed_output
    assert isinstance(parsed, EvidenceMatrixBatch)
    return StageOutput(parsed.rows, _metadata_ref(context.project_id, result))


def analyze_conflicts_and_gaps(
    context: EvidenceReviewContext,
    rows: list[EvidenceMatrixRow],
    generator: StructuredGenerator,
    registry: PromptRegistry,
    model: str,
) -> StageOutput[tuple[EvidenceConflictMap, ResearchGapReport]]:
    system, user = registry.render(
        "conflicts_gaps",
        "evidence-review-v1",
        payload=_json([row.model_dump(mode="json") for row in rows]),
    )
    result = generator.generate(
        system_prompt=system,
        user_prompt=user,
        response_model=ConflictGapResponse,
        model=model,
        prompt_version="evidence-review-v1",
    )
    parsed = result.parsed_output
    assert isinstance(parsed, ConflictGapResponse)
    return StageOutput(
        (parsed.conflict_map, parsed.gap_report),
        _metadata_ref(context.project_id, result),
    )


def synthesize_bounded_evidence(
    context: EvidenceReviewContext,
    rows: list[EvidenceMatrixRow],
    conflicts: EvidenceConflictMap,
    gaps: ResearchGapReport,
    generator: StructuredGenerator,
    registry: PromptRegistry,
    model: str,
) -> StageOutput[BoundedEvidenceSynthesis]:
    payload = {
        "project_id": context.project_id,
        "scope": context.research_scope,
        "rows": [row.model_dump(mode="json") for row in rows],
        "conflicts": conflicts.model_dump(mode="json"),
        "gaps": gaps.model_dump(mode="json"),
    }
    system, user = registry.render(
        "bounded_synthesis", "evidence-review-v1", payload=_json(payload)
    )
    result = generator.generate(
        system_prompt=system,
        user_prompt=user,
        response_model=SynthesisResponse,
        model=model,
        prompt_version="evidence-review-v1",
    )
    parsed = result.parsed_output
    assert isinstance(parsed, SynthesisResponse)
    return StageOutput(parsed.synthesis, _metadata_ref(context.project_id, result))


def _metadata_ref(project_id: str, result: GenerationResult) -> str:
    return f"llm-metadata://{project_id}/{result.request_id}"


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

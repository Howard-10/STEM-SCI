"""Structured-generation and deterministic validation stages for writing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Generic, Literal, TypeVar

from stem_sci.agents.runtime import GenerationResult, PromptRegistry, StructuredGenerator

from .models import (
    AtomicClaimGraph,
    ClaimGraphResponse,
    DraftResponse,
    ManuscriptDraft,
    ManuscriptOutline,
    OutlineResponse,
    WritingContextBundle,
    WritingSufficiencyReport,
    WritingSufficiencyStatus,
)

T = TypeVar("T")


@dataclass(frozen=True)
class StageOutput(Generic[T]):
    value: T
    metadata_ref: str


def audit_writing_inputs(context: WritingContextBundle) -> WritingSufficiencyReport:
    missing: list[str] = []
    if not context.evidence_refs:
        missing.append("verified_evidence")
    elif context.intended_use == "formal" and not any(
        item.verification_status.value in {"source_verified", "human_verified"}
        for item in context.evidence_refs
    ):
        missing.append("formal_verified_evidence")
    if not context.approved_study_protocol_refs:
        missing.append("approved_study_protocol")
    if not context.validated_result_cards:
        missing.append("validated_result_cards")
    return WritingSufficiencyReport(
        report_id=f"writing-sufficiency-{context.project_id}",
        project_id=context.project_id,
        status=WritingSufficiencyStatus.READY if not missing else WritingSufficiencyStatus.INCOMPLETE,
        missing_requirements=missing,
    )


def build_claim_graph(
    context: WritingContextBundle,
    generator: StructuredGenerator,
    registry: PromptRegistry,
    model: str,
) -> StageOutput[AtomicClaimGraph]:
    payload = {
        "project_id": context.project_id,
        "scope": context.approved_research_scope,
        "evidence": [item.model_dump(mode="json") for item in context.evidence_refs],
        "validated_result_cards": context.validated_result_cards,
        "approved_protocols": context.approved_study_protocol_refs,
        "interpretation_boundaries": context.interpretation_boundaries,
    }
    system, user = registry.render("claim_graph", "paper-writing-v1", payload=_json(payload))
    result = generator.generate(
        system_prompt=system,
        user_prompt=user,
        response_model=ClaimGraphResponse,
        model=model,
        prompt_version="paper-writing-v1",
    )
    parsed = result.parsed_output
    assert isinstance(parsed, ClaimGraphResponse)
    return StageOutput(parsed.graph, _metadata_ref(context.project_id, result))


def build_manuscript_outline(
    context: WritingContextBundle,
    graph: AtomicClaimGraph,
    generator: StructuredGenerator,
    registry: PromptRegistry,
    model: str,
) -> StageOutput[ManuscriptOutline]:
    system, user = registry.render(
        "outline",
        "paper-writing-v1",
        payload=_json(graph.model_dump(mode="json")),
    )
    result = generator.generate(
        system_prompt=system,
        user_prompt=user,
        response_model=OutlineResponse,
        model=model,
        prompt_version="paper-writing-v1",
    )
    parsed = result.parsed_output
    assert isinstance(parsed, OutlineResponse)
    return StageOutput(parsed.outline, _metadata_ref(context.project_id, result))


def render_manuscript(
    language: Literal["zh-CN", "en-US"],
    context: WritingContextBundle,
    graph: AtomicClaimGraph,
    outline: ManuscriptOutline,
    generator: StructuredGenerator,
    registry: PromptRegistry,
    model: str,
) -> StageOutput[ManuscriptDraft]:
    prompt_name = "draft_zh" if language == "zh-CN" else "draft_en"
    payload = {"language": language, "graph": graph.model_dump(mode="json"), "outline": outline.model_dump(mode="json")}
    system, user = registry.render(prompt_name, "paper-writing-v1", payload=_json(payload))
    result = generator.generate(
        system_prompt=system,
        user_prompt=user,
        response_model=DraftResponse,
        model=model,
        prompt_version="paper-writing-v1",
    )
    parsed = result.parsed_output
    assert isinstance(parsed, DraftResponse)
    return StageOutput(parsed.draft, _metadata_ref(context.project_id, result))


def validate_manuscript(
    draft: ManuscriptDraft,
    graph: AtomicClaimGraph,
    context: WritingContextBundle,
) -> list[str]:
    issues: list[str] = []
    graph_ids = {node.claim_id for node in graph.nodes}
    evidence_ids = {item.evidence_id for item in context.evidence_refs}
    if draft.project_id != context.project_id:
        issues.append("WRITING_PROJECT_MISMATCH")
    if not set(draft.claim_ids).issubset(graph_ids):
        issues.append("WRITING_UNKNOWN_CLAIM")
    if not set(draft.citation_refs).issubset(evidence_ids):
        issues.append("WRITING_UNKNOWN_CITATION")
    return issues


def normalize_draft(draft: ManuscriptDraft, graph: AtomicClaimGraph) -> ManuscriptDraft:
    graph_ids = {node.claim_id for node in graph.nodes}
    claim_ids = [claim_id for claim_id in draft.claim_ids if claim_id in graph_ids]
    directions = {key: value for key, value in draft.result_directions.items() if key in graph_ids}
    strengths = {key: value for key, value in draft.claim_strengths.items() if key in graph_ids}
    limitations = [claim_id for claim_id in draft.limitation_claim_ids if claim_id in graph_ids]
    return draft.model_copy(
        update={
            "claim_ids": claim_ids,
            "result_directions": directions,
            "claim_strengths": strengths,
            "limitation_claim_ids": limitations,
        }
    )


def _metadata_ref(project_id: str, result: GenerationResult) -> str:
    return f"llm-metadata://{project_id}/{result.request_id}"


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

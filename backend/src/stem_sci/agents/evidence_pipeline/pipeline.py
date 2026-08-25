"""Orchestration for bounded-corpus evidence synthesis."""

from __future__ import annotations

from stem_sci.agents.contracts import AgentInput
from stem_sci.agents.runtime import PromptRegistry, StructuredGenerator

from .models import (
    BoundedEvidenceSynthesis,
    EvidenceConflictMap,
    EvidenceMatrixRow,
    EvidenceReviewContext,
    EvidenceReviewPackage,
    EvidenceSufficiencyReport,
    PackageStatus,
    PaperCard,
    ResearchGapReport,
)
from .prompts import register_evidence_prompts
from .stages import (
    analyze_conflicts_and_gaps,
    audit_corpus,
    build_evidence_matrix,
    extract_paper_cards,
    screen_sources,
    synthesize_bounded_evidence,
)
from .validators import validate_evidence_context

CORPUS_LIMIT_PREFIX = "在当前限定语料中"


class EvidenceReviewPipeline:
    def __init__(
        self,
        *,
        generator: StructuredGenerator,
        model: str,
        prompt_registry: PromptRegistry | None = None,
    ) -> None:
        self.generator = generator
        self.model = model
        self.prompt_registry = prompt_registry or PromptRegistry()
        register_evidence_prompts(self.prompt_registry)

    def run(
        self, context: EvidenceReviewContext, agent_input: AgentInput
    ) -> EvidenceReviewPackage:
        del agent_input
        validate_evidence_context(context)
        coverage = audit_corpus(context)
        sufficiency = EvidenceSufficiencyReport(
            report_id=f"sufficiency-{context.project_id}",
            project_id=context.project_id,
            status=PackageStatus.READY if context.evidence_refs else PackageStatus.INCOMPLETE,
            evidence_count=len(context.evidence_refs),
            missing_requirements=[] if context.evidence_refs else ["verified_evidence"],
        )
        if not context.evidence_refs:
            return EvidenceReviewPackage(
                project_id=context.project_id,
                status=PackageStatus.INCOMPLETE,
                coverage_report=coverage,
                sufficiency=sufficiency,
                risk_flags=["INSUFFICIENT_CORPUS_COVERAGE"],
                unresolved_questions=["Add verified project evidence before synthesis."],
            )

        allowed_ids = {item.evidence_id for item in context.evidence_refs}
        allowed_sources = set(context.source_refs)
        risk_flags: list[str] = []
        metadata_refs: list[str] = []
        decisions = screen_sources(context, coverage)

        cards_stage = extract_paper_cards(
            context, decisions, self.generator, self.prompt_registry, self.model
        )
        metadata_refs.append(cards_stage.metadata_ref)
        cards = _valid_cards(
            cards_stage.value, context.project_id, allowed_sources, allowed_ids, risk_flags
        )
        if not cards:
            risk_flags.append("NO_VALID_PAPER_CARDS")

        matrix_stage = build_evidence_matrix(
            context, cards, self.generator, self.prompt_registry, self.model
        )
        metadata_refs.append(matrix_stage.metadata_ref)
        rows = _valid_rows(
            matrix_stage.value, context.project_id, allowed_sources, allowed_ids, risk_flags
        )
        if not rows:
            risk_flags.append("NO_VALID_EVIDENCE_MATRIX_ROWS")

        conflict_stage = analyze_conflicts_and_gaps(
            context, rows, self.generator, self.prompt_registry, self.model
        )
        metadata_refs.append(conflict_stage.metadata_ref)
        conflict_map, gap_report = conflict_stage.value
        conflict_map = _valid_conflicts(
            conflict_map, context.project_id, allowed_ids, risk_flags
        )
        gap_report = _valid_gaps(gap_report, context.project_id, allowed_ids, risk_flags)

        synthesis_stage = synthesize_bounded_evidence(
            context,
            rows,
            conflict_map,
            gap_report,
            self.generator,
            self.prompt_registry,
            self.model,
        )
        metadata_refs.append(synthesis_stage.metadata_ref)
        synthesis = _valid_synthesis(
            synthesis_stage.value, context.project_id, allowed_ids, risk_flags
        )
        missing_requirements: list[str] = []
        if not cards:
            missing_requirements.append("valid_paper_cards")
        if not rows:
            missing_requirements.append("valid_evidence_matrix_rows")
        if synthesis is None:
            missing_requirements.append("bounded_evidence_synthesis")
        status = PackageStatus.READY if not missing_requirements else PackageStatus.INCOMPLETE
        sufficiency = sufficiency.model_copy(
            update={"status": status, "missing_requirements": missing_requirements}
        )
        used_refs = sorted(
            {
                ref
                for item_refs in [
                    *(card.evidence_refs for card in cards),
                    *(row.evidence_refs for row in rows),
                    synthesis.evidence_refs if synthesis else [],
                ]
                for ref in item_refs
                if ref in allowed_ids
            }
        )
        return EvidenceReviewPackage(
            project_id=context.project_id,
            status=status,
            coverage_report=coverage,
            screening_decisions=decisions,
            paper_cards=cards,
            evidence_matrix=rows,
            conflict_map=conflict_map,
            research_gap_report=gap_report,
            synthesis=synthesis,
            sufficiency=sufficiency,
            used_evidence_refs=used_refs,
            risk_flags=list(dict.fromkeys(risk_flags)),
            generation_metadata_refs=metadata_refs,
        )


def _refs_valid(refs: list[str], allowed_ids: set[str]) -> bool:
    return bool(refs) and set(refs).issubset(allowed_ids)


def _invalid_reference(risk_flags: list[str]) -> None:
    risk_flags.append("INVALID_EVIDENCE_REFERENCE")


def _valid_cards(
    cards: list[PaperCard],
    project_id: str,
    sources: set[str],
    evidence_ids: set[str],
    risks: list[str],
) -> list[PaperCard]:
    valid = []
    for card in cards:
        if (
            card.project_id == project_id
            and card.source_ref in sources
            and _refs_valid(card.evidence_refs, evidence_ids)
        ):
            valid.append(card)
        else:
            _invalid_reference(risks)
    return valid


def _valid_rows(
    rows: list[EvidenceMatrixRow],
    project_id: str,
    sources: set[str],
    evidence_ids: set[str],
    risks: list[str],
) -> list[EvidenceMatrixRow]:
    valid = []
    for row in rows:
        if (
            row.project_id == project_id
            and row.source_ref in sources
            and _refs_valid(row.evidence_refs, evidence_ids)
        ):
            valid.append(row)
        else:
            _invalid_reference(risks)
    return valid


def _valid_conflicts(
    conflict_map: EvidenceConflictMap,
    project_id: str,
    evidence_ids: set[str],
    risks: list[str],
) -> EvidenceConflictMap:
    valid_conflicts = []
    for conflict in conflict_map.conflicts:
        refs = [*conflict.supporting_evidence_refs, *conflict.contrasting_evidence_refs]
        if set(refs).issubset(evidence_ids):
            valid_conflicts.append(conflict)
        else:
            _invalid_reference(risks)
    if conflict_map.project_id != project_id:
        _invalid_reference(risks)
        valid_conflicts = []
    return conflict_map.model_copy(
        update={"project_id": project_id, "conflicts": valid_conflicts}
    )


def _valid_gaps(
    report: ResearchGapReport,
    project_id: str,
    evidence_ids: set[str],
    risks: list[str],
) -> ResearchGapReport:
    valid_gaps = []
    for gap in report.gaps:
        if set(gap.evidence_refs).issubset(evidence_ids):
            valid_gaps.append(gap)
        else:
            _invalid_reference(risks)
    if report.project_id != project_id:
        _invalid_reference(risks)
        valid_gaps = []
    limit_text = report.limit_text
    if not limit_text.startswith(CORPUS_LIMIT_PREFIX):
        limit_text = f"{CORPUS_LIMIT_PREFIX}，{limit_text}"
    return report.model_copy(
        update={"project_id": project_id, "gaps": valid_gaps, "limit_text": limit_text}
    )


def _valid_synthesis(
    synthesis: BoundedEvidenceSynthesis,
    project_id: str,
    evidence_ids: set[str],
    risks: list[str],
) -> BoundedEvidenceSynthesis | None:
    if synthesis.project_id != project_id or not _refs_valid(
        synthesis.evidence_refs, evidence_ids
    ):
        _invalid_reference(risks)
        return None
    return synthesis

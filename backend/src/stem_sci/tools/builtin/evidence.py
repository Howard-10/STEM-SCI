"""Deterministic, local bounded-corpus evidence Tools.

These adapters deliberately operate only on records already imported into the
project ContextService.  They do not perform online retrieval or mutate the
formal workflow state.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from stem_sci.agents.evidence_pipeline.models import (
    BoundedEvidenceSynthesis,
    CorpusCoverageReport,
    EvidenceConflict,
    EvidenceConflictMap,
    EvidenceMatrixRow,
    PaperCard,
    ScreeningDecision,
    ScreeningStatus,
)
from stem_sci.context.models import (
    EvidenceRef,
    EvidenceSearchRequest,
    SourceChunk,
    VerificationStatus,
)
from stem_sci.context.service import ContextNotFoundError, ContextService
from stem_sci.tools.models import ToolRunStatus
from stem_sci.tools.policies import ToolPolicyError

from .common import BuiltinResult, blocked, execute_wrapped, failed


class BuiltinEvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceSearchResultSet(BuiltinEvidenceModel):
    project_id: str
    items: list[EvidenceRef] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)
    corpus_limit: str = "Only the project's imported local corpus was searched."


class VerificationReport(BuiltinEvidenceModel):
    project_id: str
    verified_refs: list[str] = Field(default_factory=list)
    unverified_refs: list[str] = Field(default_factory=list)
    status: ToolRunStatus = ToolRunStatus.SUCCEEDED
    error_code: str | None = None


class ScreeningLedger(BuiltinEvidenceModel):
    project_id: str
    decisions: list[ScreeningDecision] = Field(default_factory=list)
    criteria: list[str] = Field(default_factory=list)
    corpus_limit: str = "Screening is limited to the project's imported local corpus."


class PaperCardCollection(BuiltinEvidenceModel):
    project_id: str
    cards: list[PaperCard] = Field(default_factory=list)
    corpus_limit: str = "Paper cards were derived only from supplied source chunks."


class EvidenceMatrixCandidate(BuiltinEvidenceModel):
    project_id: str
    rows: list[EvidenceMatrixRow] = Field(default_factory=list)
    corpus_limit: str = "The matrix describes only the supplied bounded corpus."


class ValidationReport(BuiltinEvidenceModel):
    project_id: str
    approved: bool = False
    checks: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    corpus_limit: str = "Validation does not establish evidence beyond the supplied corpus."


def _project_check(project_id: str, refs: Iterable[EvidenceRef]) -> None:
    for ref in refs:
        if ref.project_id != project_id:
            raise ToolPolicyError("PROJECT_SCOPE_VIOLATION")


def _result(value: Any) -> BuiltinResult[Any]:
    return BuiltinResult(value=value)


def _resolve_verified_ids(
    project_id: str, evidence_ids: Iterable[str], service: ContextService | None
) -> tuple[list[EvidenceRef], BuiltinResult[Any] | None]:
    if service is None:
        return [], failed("PERSISTENCE_UNAVAILABLE")
    refs: list[EvidenceRef] = []
    try:
        for evidence_id in evidence_ids:
            detail = service.get_evidence(project_id, evidence_id)
            if detail.verification_status not in {
                VerificationStatus.SOURCE_VERIFIED,
                VerificationStatus.HUMAN_VERIFIED,
            }:
                return [], blocked("UNVERIFIED_EVIDENCE")
            refs.append(detail)
    except ContextNotFoundError:
        owner = service.evidence_project(evidence_id)
        return [], blocked("PROJECT_SCOPE_VIOLATION" if owner and owner != project_id else "REFERENCE_NOT_FOUND")
    return refs, None


class KnowledgeBaseSearchTool:
    tool_id = "knowledge_base_search"

    def __init__(self, service: ContextService | None = None) -> None:
        self.service = service

    def execute(self, project_id: str, query: str, limit: int = 10) -> BuiltinResult[Any]:
        service = self.service
        if service is None:
            return failed("PERSISTENCE_UNAVAILABLE")
        if not query.strip() or limit < 1:
            return failed("INVALID_INPUT")
        def search() -> EvidenceSearchResultSet:
            items = service.search(EvidenceSearchRequest(project_id=project_id, query=query, limit=min(limit, 50)))
            return EvidenceSearchResultSet(
                project_id=project_id,
                items=[item.evidence for item in items],
                scores={item.evidence.evidence_id: item.score for item in items},
            )
        return execute_wrapped(search)


class SourceChunkReaderTool:
    tool_id = "source_chunk_reader"

    def __init__(self, service: ContextService | None = None) -> None:
        self.service = service

    def execute(self, project_id: str, source_id: str, chunk_ids: Sequence[str] | None = None) -> BuiltinResult[Any]:
        service = self.service
        if service is None:
            return failed("PERSISTENCE_UNAVAILABLE")
        def read() -> list[SourceChunk]:
            chunks = service.chunks(project_id, source_id)
            if chunk_ids is None:
                return chunks
            allowed = set(chunk_ids)
            unknown = allowed.difference(chunk.chunk_id for chunk in chunks)
            if unknown:
                raise LookupError(next(iter(unknown)))
            return [chunk for chunk in chunks if chunk.chunk_id in allowed]
        return execute_wrapped(read)


class SourceVerificationCheckerTool:
    tool_id = "source_verification_checker"

    def __init__(self, service: ContextService | None = None) -> None:
        self.service = service

    def execute(
        self,
        project_id: str,
        evidence_refs: Sequence[EvidenceRef] | None = None,
        *,
        evidence_ref: EvidenceRef | None = None,
    ) -> BuiltinResult[Any]:
        refs = list(evidence_refs or ([] if evidence_ref is None else [evidence_ref]))
        try:
            _project_check(project_id, refs)
        except ToolPolicyError as error:
            return blocked(error.error_code)
        stored_refs, failure = _resolve_verified_ids(project_id, [ref.evidence_id for ref in refs], self.service)
        if failure is not None:
            return failure
        unverified: list[str] = []
        verified = [ref.evidence_id for ref in stored_refs]
        if unverified:
            return BuiltinResult(
                status=ToolRunStatus.BLOCKED,
                error_code="UNVERIFIED_EVIDENCE",
                value=VerificationReport(
                    project_id=project_id,
                    verified_refs=verified,
                    unverified_refs=unverified,
                    status=ToolRunStatus.BLOCKED,
                    error_code="UNVERIFIED_EVIDENCE",
                ),
                risk_flags=["UNVERIFIED_EVIDENCE"],
            )
        return _result(VerificationReport(project_id=project_id, verified_refs=verified))


class PaperScreeningExecutorTool:
    tool_id = "paper_screening_executor"

    def __init__(self, service: ContextService | None = None) -> None:
        self.service = service

    def execute(self, project_id: str, source_refs: Sequence[str], criteria: Sequence[str] | None = None) -> BuiltinResult[Any]:
        service = self.service
        if service is None:
            return failed("PERSISTENCE_UNAVAILABLE")
        criteria_list = list(criteria or [])
        def screen() -> ScreeningLedger:
            decisions: list[ScreeningDecision] = []
            for source_ref in sorted(set(source_refs)):
                refs = [item.evidence_id for item in service.evidence_for_source(project_id, source_ref)]
                decisions.append(
                    ScreeningDecision(
                        source_ref=source_ref,
                        decision=ScreeningStatus.INCLUDE if refs else ScreeningStatus.UNCERTAIN,
                        reason="Project evidence is available." if refs else "No project evidence matched the source.",
                        criteria_refs=criteria_list,
                        evidence_refs=refs,
                    )
                )
            return ScreeningLedger(project_id=project_id, decisions=decisions, criteria=criteria_list)
        return execute_wrapped(screen)


class PaperCardExtractorTool:
    tool_id = "paper_card_extractor"

    def __init__(self, service: ContextService | None = None) -> None:
        self.service = service

    def execute(self, project_id: str, source_chunks: Sequence[SourceChunk]) -> BuiltinResult[Any]:
        try:
            if any(chunk.project_id != project_id for chunk in source_chunks):
                raise ToolPolicyError("PROJECT_SCOPE_VIOLATION")
            grouped: dict[str, list[SourceChunk]] = defaultdict(list)
            for chunk in source_chunks:
                grouped[chunk.source_id].append(chunk)
            if self.service is None:
                return failed("PERSISTENCE_UNAVAILABLE")
            cards = [
                PaperCard(
                    paper_card_id=f"paper-card-{source_id}",
                    project_id=project_id,
                    source_ref=source_id,
                    title=next((chunk.location.heading for chunk in chunks if chunk.location.heading), source_id),
                    main_findings=[chunks[0].text[:280]],
                    evidence_refs=[self.service.evidence_for_chunk(project_id, chunk.chunk_id).evidence_id for chunk in chunks],
                )
                for source_id, chunks in sorted(grouped.items())
            ]
            return _result(PaperCardCollection(project_id=project_id, cards=cards))
        except ToolPolicyError as error:
            return blocked(error.error_code)
        except (TypeError, ValueError):
            return failed("INVALID_INPUT")


class EvidenceMatrixBuilderTool:
    tool_id = "evidence_matrix_builder"

    def __init__(self, service: ContextService | None = None) -> None:
        self.service = service

    def execute(self, project_id: str, paper_cards: Sequence[PaperCard]) -> BuiltinResult[Any]:
        try:
            if any(card.project_id != project_id for card in paper_cards):
                raise ToolPolicyError("PROJECT_SCOPE_VIOLATION")
            if self.service is None:
                return failed("PERSISTENCE_UNAVAILABLE")
            for card in paper_cards:
                _, failure = _resolve_verified_ids(project_id, card.evidence_refs, self.service)
                if failure is not None:
                    return failure
            rows = [
                EvidenceMatrixRow(
                    row_id=f"matrix-{card.paper_card_id}",
                    project_id=project_id,
                    research_question=card.research_question or "Unspecified research question",
                    source_ref=card.source_ref,
                    relation="MENTIONING",
                    finding=(card.main_findings[0] if card.main_findings else card.title),
                    evidence_refs=list(card.evidence_refs),
                )
                for card in paper_cards
            ]
            return _result(EvidenceMatrixCandidate(project_id=project_id, rows=rows))
        except ToolPolicyError as error:
            return blocked(error.error_code)
        except (TypeError, ValueError):
            return failed("INVALID_INPUT")


class CitationDeduplicatorTool:
    tool_id = "citation_deduplicator"

    def execute(self, project_id: str, evidence_refs: Sequence[EvidenceRef]) -> list[EvidenceRef] | BuiltinResult[None]:
        try:
            _project_check(project_id, evidence_refs)
            return sorted({ref.evidence_id: ref for ref in evidence_refs}.values(), key=lambda ref: ref.evidence_id)
        except ToolPolicyError as error:
            return blocked(error.error_code)


class EvidenceConflictDetectorTool:
    tool_id = "evidence_conflict_detector"

    def __init__(self, service: ContextService | None = None) -> None:
        self.service = service

    def execute(self, project_id: str, matrix: EvidenceMatrixCandidate | Sequence[EvidenceMatrixRow]) -> BuiltinResult[Any]:
        rows = matrix.rows if isinstance(matrix, EvidenceMatrixCandidate) else list(matrix)
        try:
            if any(row.project_id != project_id for row in rows):
                raise ToolPolicyError("PROJECT_SCOPE_VIOLATION")
            if self.service is None:
                return failed("PERSISTENCE_UNAVAILABLE")
            for row in rows:
                _, failure = _resolve_verified_ids(project_id, row.evidence_refs, self.service)
                if failure is not None:
                    return failure
            groups: dict[str, list[EvidenceMatrixRow]] = defaultdict(list)
            for row in rows:
                groups[row.research_question].append(row)
            conflicts: list[EvidenceConflict] = []
            for question, question_rows in sorted(groups.items()):
                supporting = [ref for row in question_rows if row.relation == "SUPPORTING" for ref in row.evidence_refs]
                contrasting = [ref for row in question_rows if row.relation == "CONTRASTING" for ref in row.evidence_refs]
                if supporting and contrasting:
                    conflicts.append(EvidenceConflict(conflict_id=f"conflict-{len(conflicts) + 1}", description=question, supporting_evidence_refs=supporting, contrasting_evidence_refs=contrasting))
            return _result(EvidenceConflictMap(map_id=f"conflicts-{project_id}", project_id=project_id, conflicts=conflicts))
        except ToolPolicyError as error:
            return blocked(error.error_code)


class CorpusCoverageCalculatorTool:
    tool_id = "corpus_coverage_calculator"

    def __init__(self, service: ContextService | None = None) -> None:
        self.service = service

    def execute(self, project_id: str, matrix: EvidenceMatrixCandidate | Sequence[EvidenceMatrixRow]) -> BuiltinResult[Any]:
        rows = matrix.rows if isinstance(matrix, EvidenceMatrixCandidate) else list(matrix)
        try:
            if any(row.project_id != project_id for row in rows):
                raise ToolPolicyError("PROJECT_SCOPE_VIOLATION")
            if self.service is None:
                return failed("PERSISTENCE_UNAVAILABLE")
            for row in rows:
                _, failure = _resolve_verified_ids(project_id, row.evidence_refs, self.service)
                if failure is not None:
                    return failure
            topics = sorted({row.research_question for row in rows})
            return _result(CorpusCoverageReport(report_id=f"coverage-{project_id}", project_id=project_id, source_count=len({row.source_ref for row in rows}), evidence_count=len({ref for row in rows for ref in row.evidence_refs}), covered_topics=topics, missing_topics=[] if topics else ["bounded corpus coverage"]))
        except ToolPolicyError as error:
            return blocked(error.error_code)


class BoundedSynthesisValidatorTool:
    tool_id = "bounded_synthesis_validator"

    def __init__(self, service: ContextService | None = None) -> None:
        self.service = service

    def execute(self, project_id: str, synthesis: BoundedEvidenceSynthesis) -> BuiltinResult[Any]:
        try:
            if synthesis.project_id != project_id:
                raise ToolPolicyError("PROJECT_SCOPE_VIOLATION")
            checks: list[str] = []
            risks: list[str] = []
            if not synthesis.evidence_refs:
                risks.append("INSUFFICIENT_VERIFIED_EVIDENCE")
            else:
                _, failure = _resolve_verified_ids(project_id, synthesis.evidence_refs, self.service)
                if failure is not None:
                    return failure
                checks.append("evidence references resolve to verified project records")
            if not synthesis.corpus_limit.strip():
                risks.append("MISSING_CORPUS_LIMIT")
            else:
                checks.append("corpus limit stated")
            report = ValidationReport(project_id=project_id, approved=not risks, checks=checks, risk_flags=risks)
            return BuiltinResult(status=ToolRunStatus.SUCCEEDED if report.approved else ToolRunStatus.BLOCKED, value=report, error_code=None if report.approved else "SYNTHESIS_OUT_OF_BOUNDS", risk_flags=risks)
        except ToolPolicyError as error:
            return blocked(error.error_code)


knowledge_base_search = KnowledgeBaseSearchTool()
source_chunk_reader = SourceChunkReaderTool()
source_verification_checker = SourceVerificationCheckerTool()
paper_screening_executor = PaperScreeningExecutorTool()
paper_card_extractor = PaperCardExtractorTool()
evidence_matrix_builder = EvidenceMatrixBuilderTool()
citation_deduplicator = CitationDeduplicatorTool()
evidence_conflict_detector = EvidenceConflictDetectorTool()
corpus_coverage_calculator = CorpusCoverageCalculatorTool()
bounded_synthesis_validator = BoundedSynthesisValidatorTool()

__all__ = [
    "BoundedSynthesisValidatorTool",
    "CitationDeduplicatorTool",
    "CorpusCoverageCalculatorTool",
    "EvidenceConflictDetectorTool",
    "EvidenceMatrixBuilderTool",
    "EvidenceSearchResultSet",
    "KnowledgeBaseSearchTool",
    "PaperCardCollection",
    "PaperCardExtractorTool",
    "PaperScreeningExecutorTool",
    "ScreeningLedger",
    "SourceChunkReaderTool",
    "SourceVerificationCheckerTool",
    "ValidationReport",
    "VerificationReport",
    "bounded_synthesis_validator",
    "citation_deduplicator",
    "corpus_coverage_calculator",
    "evidence_conflict_detector",
    "evidence_matrix_builder",
    "knowledge_base_search",
    "paper_card_extractor",
    "paper_screening_executor",
    "source_chunk_reader",
    "source_verification_checker",
]

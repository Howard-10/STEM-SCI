"""Evidence-review Agent role boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from pydantic import JsonValue

from stem_sci.context.models import ContextBundle, EvidenceRef, VerificationStatus
from stem_sci.settings import allow_unverified_formal_evidence

from .base import BaseAgent
from .contracts import AgentInput, AgentResult, CandidateArtifact, ToolRequest
from .evidence_pipeline import (
    CorpusCoverageReport,
    EvidenceConflictMap,
    EvidenceMatrixRow,
    EvidenceReviewContext,
    EvidenceReviewPackage,
    EvidenceReviewPipeline,
    EvidenceSufficiencyReport,
    PackageStatus,
    PaperCard,
    ResearchGapReport,
    ScreeningDecision,
    ScreeningStatus,
)
from .runtime import StructuredGenerationError


class EvidenceReviewAgent(BaseAgent):
    agent_id = "evidence_review"
    supported_task_types = ("design_search_protocol", "screen_evidence", "synthesize_evidence")
    allowed_tool_capabilities = (
        "literature_search",
        "paper_screening",
        "paper_extraction",
        "source_verification",
    )
    allowed_output_types = (
        "SearchProtocolCandidate",
        "InclusionExclusionCriteria",
        "PaperCardCollection",
        "EvidenceMatrixCandidate",
        "EvidenceConflictMap",
        "ResearchGapReport",
        "EvidenceSufficiencyReport",
        "LiteratureNeedUpdate",
        "CorpusCoverageReport",
        "ScreeningLedger",
        "BoundedEvidenceSynthesis",
    )

    def __init__(self, pipeline: EvidenceReviewPipeline | None = None) -> None:
        self.pipeline = pipeline

    def run_with_context(self, agent_input: AgentInput, context: ContextBundle) -> AgentResult:
        """Create evidence candidates while preserving source references from Context MVP."""
        development_formal_mode = (
            context.context_mode == "formal" and allow_unverified_formal_evidence()
        )
        if self.pipeline is not None:
            pipeline_context = EvidenceReviewContext(
                project_id=context.project_id,
                context_bundle_ref=context.context_id,
                research_scope=context.query,
                evidence_refs=context.evidence_refs,
                source_refs=context.source_refs,
                context_hash=context.context_hash,
                intended_use="demo" if development_formal_mode else "formal",
                allowed_verification_statuses=(
                    [
                        VerificationStatus.SOURCE_VERIFIED,
                        VerificationStatus.HUMAN_VERIFIED,
                        VerificationStatus.MODEL_GENERATED_UNVERIFIED,
                    ]
                    if development_formal_mode
                    else [
                        VerificationStatus.SOURCE_VERIFIED,
                        VerificationStatus.HUMAN_VERIFIED,
                    ]
                ),
            )
            try:
                result = self.run_pipeline(agent_input, pipeline_context)
            except StructuredGenerationError:
                result = self._fallback_with_generation_failure(agent_input, context)
            return self._prepare_result(
                result,
                agent_input,
                context,
                development_formal_mode,
            )
        return self._prepare_result(
            self._deterministic_result(agent_input, context),
            agent_input,
            context,
            development_formal_mode,
        )

    def _prepare_result(
        self,
        result: AgentResult,
        agent_input: AgentInput,
        context: ContextBundle,
        development_formal_mode: bool,
    ) -> AgentResult:
        """Attach the bounded operator requests used by the evidence route."""
        requested = {
            request.capability for request in result.tool_requests
        }
        operator_requests = [
            ToolRequest(
                request_id=f"{agent_input.agent_run_id}:tool:{capability}",
                capability=capability,
                input_refs=[context.context_id],
                reason=f"EvidenceReview requires {capability} for the bounded evidence package.",
            )
            for capability in (
                "paper_screening",
                "paper_extraction",
                "source_verification",
            )
            if capability not in requested
        ]
        prepared = result.model_copy(
            update={"tool_requests": [*result.tool_requests, *operator_requests]}
        )
        return self._mark_development_evidence(prepared, development_formal_mode)

    @staticmethod
    def _mark_development_evidence(
        result: AgentResult, development_formal_mode: bool
    ) -> AgentResult:
        if not development_formal_mode:
            return result
        return result.model_copy(
            update={
                "risk_flags": list(
                    dict.fromkeys([*result.risk_flags, "UNVERIFIED_FORMAL_EVIDENCE_ENABLED"])
                ),
                "recommendations": [
                    *result.recommendations,
                    "Development mode only: retrieved evidence is unverified and must not support production claims.",
                ],
            }
        )

    def _deterministic_result(self, agent_input: AgentInput, context: ContextBundle) -> AgentResult:
        package = self._deterministic_fallback(context)
        allowed = set(agent_input.allowed_output_types)
        artifacts = self._candidate_artifacts(agent_input, package, allowed)
        fallback_payloads: list[tuple[str, dict[str, object]]] = [
            (
                "SearchProtocolCandidate",
                {
                    "project_id": context.project_id,
                    "query": context.query,
                    "mode": "deterministic_context_only",
                    "source_refs": context.source_refs,
                },
            ),
            (
                "InclusionExclusionCriteria",
                {
                    "include": ["Evidence is present in the supplied ContextBundle."],
                    "exclude": ["Sources absent from the supplied ContextBundle."],
                },
            ),
            (
                "LiteratureNeedUpdate",
                {
                    "status": "MODEL_SYNTHESIS_PENDING",
                    "reason": "Deterministic fallback does not infer cross-source conclusions.",
                },
            ),
        ]
        for artifact_type, body in fallback_payloads:
            if artifact_type in allowed:
                artifacts.append(self._artifact(agent_input.task_ref, artifact_type, body))
        return AgentResult(
            agent_run_id=agent_input.agent_run_id,
            agent_id=self.agent_id,
            agent_version="phase1-deterministic-evidence-v1",
            candidate_artifact_refs=[artifact.candidate_ref for artifact in artifacts],
            candidate_artifacts=artifacts,
            evidence_refs=package.used_evidence_refs,
            risk_flags=list(dict.fromkeys([*package.risk_flags, *context.risk_flags])),
            unresolved_questions=list(
                dict.fromkeys([*package.unresolved_questions, *context.unresolved_questions])
            ),
            recommendations=[
                "Deterministic fallback organizes supplied evidence but does not create a formal synthesis.",
                "Source evidence must be verified before supporting a formal claim.",
            ],
            confidence=0.4 if package.used_evidence_refs else 0.0,
            created_at=datetime.now(UTC),
        )

    def _fallback_with_generation_failure(
        self, agent_input: AgentInput, context: ContextBundle
    ) -> AgentResult:
        fallback = self._deterministic_result(agent_input, context)
        return fallback.model_copy(
            update={
                "risk_flags": [*fallback.risk_flags, "MODEL_GENERATION_FAILED"],
                "unresolved_questions": [
                    *fallback.unresolved_questions,
                    "Model-assisted evidence synthesis is unavailable; deterministic evidence organization remains incomplete.",
                ],
            }
        )

    def run_pipeline(
        self, agent_input: AgentInput, context: EvidenceReviewContext
    ) -> AgentResult:
        if self.pipeline is None:
            raise ValueError("evidence review pipeline is not configured")
        package = self.pipeline.run(context, agent_input)
        allowed = set(agent_input.allowed_output_types)
        artifacts = self._candidate_artifacts(agent_input, package, allowed)
        refs = [artifact.candidate_ref for artifact in artifacts]
        return AgentResult(
            agent_run_id=agent_input.agent_run_id,
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            candidate_artifact_refs=refs,
            candidate_artifacts=artifacts,
            evidence_refs=package.used_evidence_refs,
            llm_metadata_refs=package.generation_metadata_refs,
            risk_flags=package.risk_flags,
            unresolved_questions=package.unresolved_questions,
            recommendations=[
                "Controller must validate the bounded evidence package before progression."
            ],
            confidence=1.0 if package.status.value == "READY" else 0.0,
            created_at=datetime.now(UTC),
        )

    def _candidate_artifacts(
        self,
        agent_input: AgentInput,
        package: EvidenceReviewPackage,
        allowed: set[str],
    ) -> list[CandidateArtifact]:
        payloads: list[tuple[str, dict[str, JsonValue]]] = []
        if package.coverage_report is not None:
            payloads.append(
                ("CorpusCoverageReport", package.coverage_report.model_dump(mode="json"))
            )
        payloads.append(
            ("EvidenceSufficiencyReport", package.sufficiency.model_dump(mode="json"))
        )
        if package.screening_decisions:
            payloads.append(
                (
                    "ScreeningLedger",
                    {
                        "decisions": [
                            item.model_dump(mode="json")
                            for item in package.screening_decisions
                        ]
                    },
                )
            )
        if package.paper_cards:
            payloads.append(
                (
                    "PaperCardCollection",
                    {"cards": [item.model_dump(mode="json") for item in package.paper_cards]},
                )
            )
        if package.evidence_matrix:
            payloads.append(
                (
                    "EvidenceMatrixCandidate",
                    {"rows": [item.model_dump(mode="json") for item in package.evidence_matrix]},
                )
            )
        if package.conflict_map is not None:
            payloads.append(
                ("EvidenceConflictMap", package.conflict_map.model_dump(mode="json"))
            )
        if package.research_gap_report is not None:
            payloads.append(
                ("ResearchGapReport", package.research_gap_report.model_dump(mode="json"))
            )
        if package.synthesis is not None:
            payloads.append(
                ("BoundedEvidenceSynthesis", package.synthesis.model_dump(mode="json"))
            )
        return [
            CandidateArtifact(
                candidate_ref=(
                    f"candidate://{self.agent_id}/{agent_input.task_ref}/{artifact_type}"
                ),
                artifact_type=artifact_type,
                schema_version="v1",
                body=body,
            )
            for artifact_type, body in payloads
            if artifact_type in allowed
        ]

    def _deterministic_fallback(self, context: ContextBundle) -> EvidenceReviewPackage:
        """Organize existing evidence without interpreting it or calling a model."""

        evidence_by_source: dict[str, list[EvidenceRef]] = {}
        for evidence in context.evidence_refs:
            evidence_by_source.setdefault(evidence.source_id, []).append(evidence)
        decisions = [
            ScreeningDecision(
                source_ref=source_ref,
                decision=ScreeningStatus.INCLUDE,
                reason="A project-scoped evidence reference is present in the ContextBundle.",
                evidence_refs=[item.evidence_id for item in refs],
            )
            for source_ref, refs in sorted(evidence_by_source.items())
        ]
        cards = [
            PaperCard(
                paper_card_id=f"deterministic-card:{context.project_id}:{source_ref}",
                project_id=context.project_id,
                source_ref=source_ref,
                title=f"Source {source_ref}",
                main_findings=[item.excerpt for item in refs],
                limitations=["Deterministic fallback preserves excerpts but performs no semantic extraction."],
                evidence_refs=[item.evidence_id for item in refs],
            )
            for source_ref, refs in sorted(evidence_by_source.items())
        ]
        rows = [
            EvidenceMatrixRow(
                row_id=f"deterministic-row:{context.project_id}:{evidence.evidence_id}",
                project_id=context.project_id,
                research_question=context.query,
                source_ref=evidence.source_id,
                relation="MENTIONING",
                finding=evidence.excerpt,
                applicability_boundary="Excerpt retained without model-generated support or contrast inference.",
                evidence_refs=[evidence.evidence_id],
            )
            for evidence in context.evidence_refs
        ]
        coverage = CorpusCoverageReport(
            report_id=f"deterministic-coverage:{context.context_id}",
            project_id=context.project_id,
            source_count=len(evidence_by_source),
            evidence_count=len(context.evidence_refs),
            covered_topics=[context.query] if context.evidence_refs else [],
            missing_topics=[] if context.evidence_refs else [context.query],
        )
        missing = ["model_assisted_bounded_synthesis"]
        if not context.evidence_refs:
            missing.insert(0, "verified_evidence")
        return EvidenceReviewPackage(
            project_id=context.project_id,
            status=PackageStatus.INCOMPLETE,
            coverage_report=coverage,
            screening_decisions=decisions,
            paper_cards=cards,
            evidence_matrix=rows,
            conflict_map=EvidenceConflictMap(
                map_id=f"deterministic-conflicts:{context.context_id}",
                project_id=context.project_id,
                conflicts=[],
            ),
            research_gap_report=ResearchGapReport(
                report_id=f"deterministic-gaps:{context.context_id}",
                project_id=context.project_id,
                gaps=[],
                limit_text="Deterministic fallback does not infer research gaps from source excerpts.",
            ),
            sufficiency=EvidenceSufficiencyReport(
                report_id=f"deterministic-sufficiency:{context.context_id}",
                project_id=context.project_id,
                status=PackageStatus.INCOMPLETE,
                evidence_count=len(context.evidence_refs),
                missing_requirements=missing,
            ),
            used_evidence_refs=[item.evidence_id for item in context.evidence_refs],
            risk_flags=["MODEL_SYNTHESIS_NOT_CONFIGURED"],
            unresolved_questions=[
                "Configure a structured model pipeline before producing conflict analysis or a bounded synthesis."
            ],
        )

    def _artifact(
        self, task_ref: str, artifact_type: str, body: dict[str, object]
    ) -> CandidateArtifact:
        return CandidateArtifact(
            candidate_ref=f"candidate://{self.agent_id}/{task_ref}/{artifact_type}",
            artifact_type=artifact_type,
            schema_version="v1",
            body=cast(dict[str, JsonValue], body),
        )

"""Evidence-review Agent role boundary."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import JsonValue

from stem_sci.context.models import ContextBundle

from .base import BaseAgent
from .contracts import AgentInput, AgentResult, CandidateArtifact
from .evidence_pipeline import EvidenceReviewContext, EvidenceReviewPackage, EvidenceReviewPipeline


class EvidenceReviewAgent(BaseAgent):
    agent_id = "evidence_review"
    skill_ids = ("bounded_corpus_review@v1", "source_screening@v1", "citation_grounding@v1")
    tool_ids = (
        "context_bundle_read@v1",
        "knowledge_base_search@v1",
        "source_verification_checker@v1",
        "evidence_ref_validate@v1",
    )
    supported_task_types = ("design_search_protocol", "screen_evidence", "synthesize_evidence")
    allowed_tool_capabilities = (
        "literature_search",
        "paper_screening",
        "paper_extraction",
        "source_verification",
        "knowledge_base_search@v1",
        "source_verification_checker@v1",
        "bounded_synthesis_validator@v1",
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
        if self.pipeline is not None:
            pipeline_context = EvidenceReviewContext(
                project_id=context.project_id,
                context_bundle_ref=context.context_id,
                research_scope=context.query,
                evidence_refs=context.evidence_refs,
                source_refs=context.source_refs,
                context_hash=context.context_hash,
            )
            return self.run_pipeline(agent_input, pipeline_context)
        result = self.run(agent_input)
        risk_flags = list(result.risk_flags)
        unresolved_questions = [*result.unresolved_questions, *context.unresolved_questions]
        if not context.evidence_refs:
            risk_flags.append("INSUFFICIENT_VERIFIED_EVIDENCE")
        return result.model_copy(
            update={
                "evidence_refs": [evidence.evidence_id for evidence in context.evidence_refs],
                "risk_flags": list(dict.fromkeys([*risk_flags, *context.risk_flags])),
                "unresolved_questions": list(dict.fromkeys(unresolved_questions)),
                "recommendations": [
                    *result.recommendations,
                    "Source evidence must be verified before supporting a formal claim.",
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

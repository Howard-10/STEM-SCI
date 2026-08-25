"""Paper-writing Agent role boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from pydantic import JsonValue

from stem_sci.core.claims import ClaimType

from .base import BaseAgent
from .contracts import AgentInput, AgentResult, CandidateArtifact
from .writing_pipeline import (
    AtomicClaimGraph,
    AtomicClaimNode,
    BilingualConsistencyReport,
    BilingualConsistencyStatus,
    LanguageCode,
    ManuscriptDraft,
    ManuscriptOutline,
    PaperWritingPipeline,
    WritingContextBundle,
    WritingSufficiencyReport,
    WritingSufficiencyStatus,
)
from .runtime import StructuredGenerationError


class PaperWritingAgent(BaseAgent):
    agent_id = "paper_writing"
    supported_task_types = ("draft_manuscript", "map_claims_to_evidence", "draft_reproducibility_statement")
    allowed_tool_capabilities = ()
    allowed_output_types = (
        "AtomicClaimCandidate",
        "ClaimEvidenceMap",
        "ManuscriptOutline",
        "ManuscriptDraft",
        "AbstractDraft",
        "TableFigureNarrative",
        "LimitationsDraft",
        "ReproducibilityStatement",
        "AtomicClaimGraph",
        "ManuscriptDraftZh",
        "ManuscriptDraftEn",
        "BilingualConsistencyReport",
        "WritingSufficiencyReport",
    )

    def __init__(self, pipeline: PaperWritingPipeline | None = None) -> None:
        self.pipeline = pipeline

    def run_pipeline(
        self, agent_input: AgentInput, context: WritingContextBundle
    ) -> AgentResult:
        if self.pipeline is None:
            raise ValueError("paper writing pipeline is not configured")
        package = self.pipeline.run(context, agent_input)
        allowed = set(agent_input.allowed_output_types)
        payloads: list[tuple[str, dict[str, object]]] = [
            ("AtomicClaimGraph", package.claim_graph.model_dump(mode="json")),
            ("ManuscriptOutline", package.outline.model_dump(mode="json") if package.outline else {}),
            ("ManuscriptDraftZh", package.chinese.model_dump(mode="json")),
            ("ManuscriptDraftEn", package.english.model_dump(mode="json")),
            ("BilingualConsistencyReport", package.consistency.model_dump(mode="json")),
            ("WritingSufficiencyReport", package.sufficiency.model_dump(mode="json")),
        ]
        artifacts = [
            CandidateArtifact(
                candidate_ref=f"candidate://{self.agent_id}/{agent_input.task_ref}/{artifact_type}",
                artifact_type=artifact_type,
                schema_version="v1",
                body=cast(dict[str, JsonValue], body),
            )
            for artifact_type, body in payloads
            if artifact_type in allowed
        ]
        return AgentResult(
            agent_run_id=agent_input.agent_run_id,
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            candidate_artifact_refs=[artifact.candidate_ref for artifact in artifacts],
            candidate_artifacts=artifacts,
            evidence_refs=list(
                dict.fromkeys(
                    ref
                    for claim in package.claim_graph.nodes
                    for ref in claim.evidence_refs
                )
            ),
            llm_metadata_refs=package.generation_metadata_refs,
            risk_flags=package.risk_flags,
            unresolved_questions=package.sufficiency.missing_requirements,
            recommendations=[
                "Controller must validate the bilingual manuscript package before progression."
            ],
            confidence=1.0 if not package.risk_flags else 0.0,
            created_at=datetime.now(UTC),
        )

    def run_with_context(
        self, agent_input: AgentInput, context: WritingContextBundle
    ) -> AgentResult:
        """Run the writing pipeline for a Controller-created project context."""
        if self.pipeline is None:
            return self._deterministic_fallback(agent_input, context)
        try:
            return self.run_pipeline(agent_input, context)
        except StructuredGenerationError:
            fallback = self._deterministic_fallback(agent_input, context)
            return fallback.model_copy(
                update={
                    "risk_flags": [*fallback.risk_flags, "MODEL_GENERATION_FAILED"],
                    "unresolved_questions": [
                        *fallback.unresolved_questions,
                        "Model-assisted manuscript generation is unavailable; deterministic skeleton remains incomplete.",
                    ],
                }
            )

    def _deterministic_fallback(
        self, agent_input: AgentInput, context: WritingContextBundle
    ) -> AgentResult:
        """Produce a traceable manuscript skeleton without inferring findings.

        The fallback deliberately writes no literature conclusion and no result
        number.  It only records controller-supplied protocol/result references
        and makes the absence of model-generated prose explicit.
        """

        nodes: list[AtomicClaimNode] = [
            AtomicClaimNode(
                project_id=context.project_id,
                claim_id=f"{context.project_id}:limitation:deterministic-fallback",
                text=(
                    "This candidate manuscript is bounded to supplied references and does not "
                    "include model-generated literature synthesis or result interpretation."
                ),
                claim_type=ClaimType.LIMITATION,
                section_target="limitations",
                strength="bounded",
            )
        ]
        if context.approved_study_protocol_refs:
            nodes.insert(
                0,
                AtomicClaimNode(
                    project_id=context.project_id,
                    claim_id=f"{context.project_id}:method:approved-protocol",
                    text="The candidate manuscript records an approved study protocol reference.",
                    claim_type=ClaimType.METHOD,
                    method_ref=context.approved_study_protocol_refs[0],
                    section_target="methods",
                    strength="bounded",
                ),
            )
        graph = AtomicClaimGraph(project_id=context.project_id, nodes=nodes)
        outline = ManuscriptOutline(
            outline_id=f"deterministic-outline:{context.project_id}",
            project_id=context.project_id,
            title=f"Candidate manuscript: {context.approved_research_scope}",
            section_claim_ids={
                "methods": [node.claim_id for node in nodes if node.claim_type is ClaimType.METHOD],
                "limitations": [node.claim_id for node in nodes if node.claim_type is ClaimType.LIMITATION],
            },
        )
        drafts = [
            ManuscriptDraft(
                project_id=context.project_id,
                language=LanguageCode.ZH_CN,
                sections={
                    "methods": "本候选草稿仅保留已批准研究协议的引用，不新增方法主张。",
                    "results": "已提供验证结果卡引用；确定性降级模式不转写统计数字或结果方向。",
                    "limitations": "尚未进行模型驱动的文献综合、结果解释或正式论文表述。",
                },
                claim_ids=[node.claim_id for node in nodes],
                status="INCOMPLETE_CANDIDATE",
            ),
            ManuscriptDraft(
                project_id=context.project_id,
                language=LanguageCode.EN_US,
                sections={
                    "methods": "This candidate retains approved protocol references only and adds no method claim.",
                    "results": "Validated result-card references are available; deterministic fallback renders no statistics or direction.",
                    "limitations": "Model-assisted literature synthesis, interpretation, and formal prose remain incomplete.",
                },
                claim_ids=[node.claim_id for node in nodes],
                status="INCOMPLETE_CANDIDATE",
            ),
        ]
        sufficiency = WritingSufficiencyReport(
            report_id=f"deterministic-writing-sufficiency:{context.project_id}",
            project_id=context.project_id,
            status=WritingSufficiencyStatus.INCOMPLETE,
            missing_requirements=[
                "model_assisted_claim_graph",
                "model_assisted_manuscript_draft",
                "human_review_of_interpretation",
            ],
        )
        consistency = BilingualConsistencyReport(
            report_id=f"deterministic-bilingual-consistency:{context.project_id}",
            project_id=context.project_id,
            status=BilingualConsistencyStatus.PASS,
            findings=["Both drafts are intentionally incomplete deterministic skeletons."],
        )
        payloads: list[tuple[str, dict[str, object]]] = [
            ("AtomicClaimGraph", graph.model_dump(mode="json")),
            ("ManuscriptOutline", outline.model_dump(mode="json")),
            ("ManuscriptDraftZh", drafts[0].model_dump(mode="json")),
            ("ManuscriptDraftEn", drafts[1].model_dump(mode="json")),
            ("BilingualConsistencyReport", consistency.model_dump(mode="json")),
            ("WritingSufficiencyReport", sufficiency.model_dump(mode="json")),
            (
                "ClaimEvidenceMap",
                {
                    "status": "INCOMPLETE",
                    "reason": "No deterministic literature or result claim is created without a model pipeline.",
                },
            ),
            (
                "ReproducibilityStatement",
                {
                    "validated_result_card_refs": context.validated_result_cards,
                    "statement": "No statistic is copied into the deterministic fallback draft.",
                },
            ),
        ]
        allowed = set(agent_input.allowed_output_types)
        artifacts = [
            CandidateArtifact(
                candidate_ref=f"candidate://{self.agent_id}/{agent_input.task_ref}/{artifact_type}",
                artifact_type=artifact_type,
                schema_version="v1",
                body=cast(dict[str, JsonValue], body),
            )
            for artifact_type, body in payloads
            if artifact_type in allowed
        ]
        return AgentResult(
            agent_run_id=agent_input.agent_run_id,
            agent_id=self.agent_id,
            agent_version="phase1-deterministic-writing-v1",
            candidate_artifact_refs=[artifact.candidate_ref for artifact in artifacts],
            candidate_artifacts=artifacts,
            evidence_refs=[item.evidence_id for item in context.evidence_refs],
            risk_flags=["WRITING_PIPELINE_NOT_CONFIGURED", "FORMAL_MANUSCRIPT_INCOMPLETE"],
            unresolved_questions=sufficiency.missing_requirements,
            recommendations=[
                "Configure the structured writing pipeline before producing formal manuscript content.",
                "Controller must validate ClaimEvidenceMap and route interpretation to human review.",
            ],
            confidence=0.3,
            created_at=datetime.now(UTC),
        )

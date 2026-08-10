"""Paper-writing Agent role boundary."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import JsonValue

from .base import BaseAgent
from .contracts import AgentInput, AgentResult, CandidateArtifact
from .writing_pipeline import PaperWritingPipeline, WritingContextBundle


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
        payloads: list[tuple[str, dict[str, JsonValue]]] = [
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
                body=body,
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
            result = self.run(agent_input)
            return result.model_copy(
                update={
                    "risk_flags": [*result.risk_flags, "WRITING_PIPELINE_NOT_CONFIGURED"],
                    "unresolved_questions": [
                        *result.unresolved_questions,
                        "Configure the GPT writing pipeline before generating manuscript content.",
                    ],
                }
            )
        return self.run_pipeline(agent_input, context)

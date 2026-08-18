from __future__ import annotations

from pathlib import Path

from stem_sci.agents import PaperWritingAgent
from stem_sci.agents.runtime import FakeLLMProvider, StructuredGenerator
from stem_sci.agents.writing_pipeline import PaperWritingPipeline
from stem_sci.artifacts.artifact_store import SQLiteArtifactStore
from stem_sci.artifacts.content_store import SQLiteArtifactContentStore
from stem_sci.context.models import ContextBundle, EvidenceRef, SourceLocation, VerificationStatus
from stem_sci.controller import (
    AgentDispatcher,
    AgentRegistry,
    ControllerWorkflowState,
    ResearchController,
)
from stem_sci.core.enums import ProjectStage
from stem_sci.core.state import ResearchState
from stem_sci.provenance.agent_run_store import SQLiteAgentRunStore


def _writing_responses(project_id: str, *, include_result: bool) -> list[dict[str, object]]:
    nodes: list[dict[str, object]] = [
        {
            "project_id": project_id,
            "claim_id": "limitation-1",
            "text": "The bounded study has limitations.",
            "claim_type": "LIMITATION",
            "section_target": "limitations",
            "strength": "bounded",
        }
    ]
    if include_result:
        nodes.insert(
            0,
            {
                "project_id": project_id,
                "claim_id": "result-claim-1",
                "text": "The validated result was positive.",
                "claim_type": "RESULT",
                "result_card_ref": "result-1",
                "section_target": "results",
                "strength": "associational",
            },
        )
    claim_ids = [str(node["claim_id"]) for node in nodes]
    strengths = {claim_id: "bounded" for claim_id in claim_ids}
    if include_result:
        strengths["result-claim-1"] = "associational"
    return [
        {"graph": {"project_id": project_id, "nodes": nodes}},
        {
            "outline": {
                "outline_id": "outline-1",
                "project_id": project_id,
                "title": "AI-supported physics modeling",
                "section_claim_ids": {
                    "results": ["result-claim-1"] if include_result else [],
                    "limitations": ["limitation-1"],
                },
            }
        },
        {
            "draft": {
                "project_id": project_id,
                "language": "zh-CN",
                "sections": {"limitations": "研究存在局限。"},
                "claim_ids": claim_ids,
                "citation_refs": ["evidence-1"],
                "numeric_literals": [],
                "result_directions": {"result-claim-1": "positive"} if include_result else {},
                "claim_strengths": strengths,
                "limitation_claim_ids": ["limitation-1"],
                "status": "CANDIDATE",
            }
        },
        {
            "draft": {
                "project_id": project_id,
                "language": "en-US",
                "sections": {"limitations": "The study has limitations."},
                "claim_ids": claim_ids,
                "citation_refs": ["evidence-1"],
                "numeric_literals": [],
                "result_directions": {"result-claim-1": "positive"} if include_result else {},
                "claim_strengths": strengths,
                "limitation_claim_ids": ["limitation-1"],
                "status": "CANDIDATE",
            }
        },
    ]


class WritingContextProvider:
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id

    def build_context(
        self, project_id: str, task_ref: str, query: str, token_budget: int
    ) -> ContextBundle:
        assert project_id == self.project_id
        evidence = EvidenceRef(
            evidence_id="evidence-1",
            project_id=project_id,
            source_id="source-1",
            chunk_id="chunk-1",
            excerpt="Verified evidence.",
            location=SourceLocation(chunk_index=0, char_start=0, char_end=18),
            verification_status=VerificationStatus.SOURCE_VERIFIED,
        )
        return ContextBundle(
            context_id=f"context-{project_id}",
            project_id=project_id,
            task_ref=task_ref,
            query=query,
            evidence_refs=[evidence],
            source_refs=["source-1"],
            verification_summary={"source_verified": 1},
            token_budget=token_budget,
            estimated_tokens=20,
            context_hash="a" * 64,
            generated_at="2026-08-10T00:00:00Z",
        )


def _make_controller(tmp_path: Path, project_id: str, *, with_results: bool) -> ResearchController:
    provider = FakeLLMProvider(_writing_responses(project_id, include_result=with_results))
    writing_agent = PaperWritingAgent(
        pipeline=PaperWritingPipeline(
            generator=StructuredGenerator(provider),
            model="gpt-test",
        )
    )
    agents = dict(AgentRegistry.default().agents)
    agents[writing_agent.agent_id] = writing_agent
    controller = ResearchController(
        dispatcher=AgentDispatcher(AgentRegistry(agents)),
        context_provider=WritingContextProvider(project_id),
        artifact_store=SQLiteArtifactStore(tmp_path / "workflow.db"),
        artifact_content_store=SQLiteArtifactContentStore(tmp_path / "workflow.db"),
        agent_run_store=SQLiteAgentRunStore(tmp_path / "workflow.db"),
    )
    state = ResearchState(
        project_id=project_id,
        current_stage=ProjectStage.ANALYZED,
        evidence_refs=["evidence-1"],
        protocol_refs=["protocol-1"],
        research_test_result_refs=["result-1"] if with_results else [],
    )
    controller._states[project_id] = state
    controller._workflow_states[project_id] = ControllerWorkflowState(
        project_id=project_id,
        current_stage=ProjectStage.ANALYZED,
        research_state=state,
    )
    controller._project_intents[project_id] = "AI-supported physics modeling"
    return controller


def test_analyzed_project_dispatches_writing_and_persists_bilingual_artifacts(tmp_path: Path) -> None:
    project_id = "writing-controller-demo"
    controller = _make_controller(tmp_path, project_id, with_results=True)

    result = controller.run_next(project_id)

    assert result.route_decision.selected_route == "paper_writing"
    content_types = {item.artifact_type for item in controller.artifact_content_store.list_project(project_id)}
    assert {
        "AtomicClaimGraph",
        "ManuscriptOutline",
        "ManuscriptDraftZh",
        "ManuscriptDraftEn",
        "BilingualConsistencyReport",
        "WritingSufficiencyReport",
    } <= content_types
    assert result.approval_request.approval_type == "manuscript"
    assert result.workflow_state.current_stage is ProjectStage.WAITING_HUMAN


def test_controller_marks_writing_incomplete_when_results_are_missing(tmp_path: Path) -> None:
    project_id = "writing-controller-no-results"
    controller = _make_controller(tmp_path, project_id, with_results=False)

    result = controller.run_next(project_id)

    assert "INCOMPLETE_RESULT_INPUT" in result.agent_result.risk_flags
    contents = controller.artifact_content_store.list_project(project_id)
    graph = next(item for item in contents if item.artifact_type == "AtomicClaimGraph")
    assert all(node["claim_type"] != "RESULT" for node in graph.body["nodes"])

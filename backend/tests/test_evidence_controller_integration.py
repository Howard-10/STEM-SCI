from pathlib import Path

from stem_sci.agents import EvidenceReviewAgent
from stem_sci.agents.evidence_pipeline import EvidenceReviewPipeline
from stem_sci.agents.runtime import FakeLLMProvider, StructuredGenerator
from stem_sci.artifacts.artifact_store import SQLiteArtifactStore
from stem_sci.artifacts.content_store import SQLiteArtifactContentStore
from stem_sci.context.models import (
    ContextBundle,
    EvidenceRef,
    SourceLocation,
    VerificationStatus,
)
from stem_sci.controller import AgentDispatcher, AgentRegistry, PlanningRequest, ResearchController
from stem_sci.provenance.agent_run_store import SQLiteAgentRunStore


class StaticContextProvider:
    def build_context(
        self, project_id: str, task_ref: str, query: str, token_budget: int
    ) -> ContextBundle:
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
            generated_at="2026-08-05T00:00:00Z",
        )


def responses(project_id: str) -> list[dict[str, object]]:
    return [
        {
            "cards": [
                {
                    "paper_card_id": "card-1",
                    "project_id": project_id,
                    "source_ref": "source-1",
                    "title": "Verified paper",
                    "evidence_refs": ["evidence-1"],
                }
            ]
        },
        {
            "rows": [
                {
                    "row_id": "row-1",
                    "project_id": project_id,
                    "research_question": "Does it work?",
                    "source_ref": "source-1",
                    "relation": "SUPPORTING",
                    "finding": "The bounded evidence supports the intervention.",
                    "evidence_refs": ["evidence-1"],
                }
            ]
        },
        {
            "conflict_map": {
                "map_id": "conflicts-1",
                "project_id": project_id,
                "conflicts": [],
            },
            "gap_report": {
                "report_id": "gaps-1",
                "project_id": project_id,
                "gaps": [],
                "limit_text": "在当前限定语料中未发现冲突研究。",
            },
        },
        {
            "synthesis": {
                "synthesis_id": "synthesis-1",
                "project_id": project_id,
                "summary": "Bounded evidence synthesis.",
                "evidence_refs": ["evidence-1"],
                "corpus_limit": "Only verified local evidence was used.",
            }
        },
    ]


def make_controller(tmp_path: Path, project_id: str) -> tuple[
    ResearchController, SQLiteArtifactContentStore, SQLiteAgentRunStore
]:
    database = tmp_path / "workflow.db"
    pipeline = EvidenceReviewPipeline(
        generator=StructuredGenerator(FakeLLMProvider(responses(project_id))),
        model="gpt-test",
    )
    agents = dict(AgentRegistry.default().agents)
    agents["evidence_review"] = EvidenceReviewAgent(pipeline=pipeline)
    content_store = SQLiteArtifactContentStore(database)
    run_store = SQLiteAgentRunStore(database)
    controller = ResearchController(
        dispatcher=AgentDispatcher(AgentRegistry(agents)),
        context_provider=StaticContextProvider(),
        artifact_store=SQLiteArtifactStore(database),
        artifact_content_store=content_store,
        agent_run_store=run_store,
    )
    return controller, content_store, run_store


def test_controller_persists_evidence_package_content_and_metadata(tmp_path: Path) -> None:
    project_id = "evidence-integration"
    controller, content_store, run_store = make_controller(tmp_path, project_id)
    planning = controller.start_planning(
        PlanningRequest(
            project_id=project_id,
            research_intent="Study AI-supported physics modeling.",
            run_id="planning-evidence-integration",
        )
    )
    controller.resume_approval(
        project_id,
        planning.approval_request,
        decision="approved",
        decided_by="researcher",
    )

    result = controller.run_next(project_id)

    assert result.route_decision.selected_route == "evidence_review"
    contents = content_store.list_project(project_id)
    content_types = {content.artifact_type for content in contents}
    assert "BoundedEvidenceSynthesis" in content_types
    assert "EvidenceSufficiencyReport" in content_types
    assert all(content.project_id == project_id for content in contents)
    run = run_store.get(project_id, result.agent_result.agent_run_id)
    assert run is not None
    assert len(run.llm_metadata_refs) == 4
    assert result.workflow_state.research_state is not None
    assert all(isinstance(ref, str) for ref in result.workflow_state.research_state.artifact_refs)


def test_verified_evidence_can_be_approved(tmp_path: Path) -> None:
    project_id = "evidence-approval-integration"
    controller, _, _ = make_controller(tmp_path, project_id)
    planning = controller.start_planning(
        PlanningRequest(
            project_id=project_id,
            research_intent="Study AI-supported physics modeling.",
            run_id="planning-evidence-approval",
        )
    )
    controller.resume_approval(
        project_id, planning.approval_request, decision="approved", decided_by="researcher"
    )

    evidence = controller.run_next(project_id)
    approved = controller.resume_approval(
        project_id, evidence.approval_request, decision="approved", decided_by="researcher"
    )

    assert approved.current_stage.value == "EVIDENCE_READY"
    assert approved.evidence_refs == ["evidence-1"]

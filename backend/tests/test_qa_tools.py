from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from stem_sci.agents.contracts import AgentResult, ApprovalRequest
from stem_sci.artifacts.models import ArtifactRef
from stem_sci.controller.router import ControllerWorkflowState, PlanningRunResult
from stem_sci.core.enums import ProjectStage
from stem_sci.knowledge.qa_tools import QAToolExecutor, tool_definitions


def test_tool_definitions_expose_bounded_read_only_capabilities() -> None:
    names = [item["function"]["name"] for item in tool_definitions()]

    assert {
        "graph_search",
        "vector_search",
        "hybrid_search",
        "paper_lookup",
        "workflow_agent",
        "start_research_workflow",
        "get_workflow_status",
        "run_next_workflow_agent",
        "get_workflow_artifacts",
        "prepare_workflow_approval",
        "external_paper_search",
    }.issubset(names)
    assert all(
        item["function"]["parameters"]["additionalProperties"] is False
        for item in tool_definitions()
    )


def test_external_search_is_explicitly_fail_closed() -> None:
    result = QAToolExecutor(object()).execute(
        name="external_paper_search",
        arguments={"query": "graph rag"},
        project_id="demo",
        default_query="graph rag",
    )

    assert result["status"] == "NOT_CONFIGURED"
    assert "external_search_not_configured" in result["risk_flags"]


def test_workflow_tool_is_proposal_only() -> None:
    result = QAToolExecutor(object()).execute(
        name="workflow_agent",
        arguments={"agent": "EvidenceReviewAgent", "task": "review sources"},
        project_id="demo",
        default_query="review sources",
    )

    assert result["mode"] == "proposal_only"
    assert "does not create" in result["message"]


class FakeWorkflowController:
    def __init__(self) -> None:
        self.approval = ApprovalRequest(
            request_id="approval-1",
            artifact_ref="candidate://demo/ResearchScope",
            approval_type="research_scope",
            reason="Review the research scope.",
            risk_summary="Candidate output is not approved.",
        )
        self.state = ControllerWorkflowState(
            project_id="demo",
            current_stage=ProjectStage.WAITING_HUMAN,
            pending_approval_ref=self.approval.request_id,
        )

    def start_planning(self, request):
        result = SimpleNamespace(
            workflow_state=self.state,
            agent_result=SimpleNamespace(agent_id="mentor_planning"),
            approval_request=self.approval,
        )
        return PlanningRunResult.model_validate(
            {
                "workflow_state": result.workflow_state.model_dump(mode="json"),
                "agent_result": AgentResult(
                    agent_run_id="run-1",
                    agent_id="mentor_planning",
                    agent_version="v1",
                    candidate_artifact_refs=["candidate://demo/ResearchScope"],
                    created_at=datetime.now(UTC),
                ),
                "approval_request": self.approval,
                "route_decision": None,
            }
        )

    def get_state(self, _: str) -> ControllerWorkflowState:
        return self.state

    def get_pending_approval(self, _: str) -> ApprovalRequest:
        return self.approval


class FakeArtifactStore:
    def list_project(self, project_id: str) -> list[ArtifactRef]:
        return [
            ArtifactRef(
                artifact_id="artifact-1",
                project_id=project_id,
                artifact_type="ResearchScope",
                version=1,
                content_uri="artifact-content://demo/artifact-1/1",
                sha256="a" * 64,
                created_at=datetime.now(UTC),
                created_by="mentor_planning",
            )
        ]


def test_workflow_tools_call_controller_and_prepare_approval() -> None:
    executor = QAToolExecutor(
        object(),
        workflow_controller=FakeWorkflowController(),
        artifact_store=FakeArtifactStore(),
    )

    started = executor.execute(
        name="start_research_workflow",
        arguments={"research_intent": "研究虚拟现实物理教学"},
        project_id="demo",
        default_query="研究虚拟现实物理教学",
    )
    assert started["status"] == "STARTED"
    assert started["workflow_action"]["selected_agent"] == "mentor_planning"

    approval = executor.execute(
        name="prepare_workflow_approval",
        arguments={},
        project_id="demo",
        default_query="批准",
    )
    assert approval["status"] == "APPROVAL_REQUIRED"
    assert approval["workflow_action"]["confirmation_required"] is True
    assert approval["workflow_action"]["approval_request_id"] == "approval-1"

    artifacts = executor.execute(
        name="get_workflow_artifacts",
        arguments={},
        project_id="demo",
        default_query="查看工件",
    )
    assert artifacts["workflow_action"]["artifacts"][0]["artifact_type"] == "ResearchScope"

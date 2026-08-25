"""Controller integration tests for the first Agent vertical slice."""

from datetime import UTC, datetime

import pytest

from stem_sci.agents import AgentResult
from stem_sci.controller import (
    AgentDispatcher,
    AgentRegistry,
    PlanningRequest,
    ProjectStage,
    ResearchController,
)
from stem_sci.controller.merger import validate_agent_result


def test_default_registry_contains_exactly_six_roles() -> None:
    registry = AgentRegistry.default()

    assert set(registry.agents) == {
        "mentor_planning",
        "evidence_review",
        "research_design",
        "data_analysis",
        "paper_writing",
        "independent_review",
    }


def test_planning_slice_pauses_for_human_approval() -> None:
    controller = ResearchController()

    run = controller.start_planning(
        PlanningRequest(
            project_id="physics-ai-demo",
            research_intent="研究生成式 AI 分层支架对师范生 Python 物理建模迁移能力的影响",
            run_id="planning-run-001",
        )
    )

    assert run.agent_result.agent_id == "mentor_planning"
    assert run.agent_result.candidate_artifact_refs
    assert run.workflow_state.current_stage == ProjectStage.WAITING_HUMAN
    assert run.workflow_state.pending_approval_ref == run.approval_request.request_id
    assert run.approval_request.artifact_ref == run.agent_result.candidate_artifact_refs[0]


def test_only_controller_approval_moves_planning_to_scoped() -> None:
    controller = ResearchController()
    run = controller.start_planning(
        PlanningRequest(project_id="physics-ai-demo", research_intent="scope", run_id="run-002")
    )

    approved_state = controller.approve_planning(run.workflow_state, run.approval_request)

    assert approved_state.current_stage == ProjectStage.SCOPED
    assert approved_state.pending_approval_ref is None
    assert run.workflow_state.current_stage == ProjectStage.WAITING_HUMAN


def test_controller_rejects_wrong_approval_request() -> None:
    controller = ResearchController()
    run = controller.start_planning(
        PlanningRequest(project_id="physics-ai-demo", research_intent="scope", run_id="run-003")
    )
    wrong_request = run.approval_request.model_copy(update={"request_id": "approval-other"})

    with pytest.raises(ValueError, match="does not match"):
        controller.approve_planning(run.workflow_state, wrong_request)


def test_result_merger_rejects_output_outside_registered_capability() -> None:
    capability = AgentRegistry.default().get("mentor_planning").capability()
    result = AgentResult(
        agent_run_id="run-004",
        agent_id="mentor_planning",
        agent_version="phase1-scaffold",
        candidate_artifact_refs=["candidate://mentor_planning/task/NotAllowed"],
        created_at=datetime.now(UTC),
    )

    with pytest.raises(ValueError, match="outside capability"):
        validate_agent_result(result, capability)


def test_dispatcher_rejects_unknown_agent() -> None:
    with pytest.raises(ValueError, match="unknown agent"):
        AgentDispatcher().dispatch("unknown", object())  # type: ignore[arg-type]

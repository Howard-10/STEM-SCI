from __future__ import annotations

import pytest
from langgraph.types import Command

from stem_sci.controller import LangGraphWorkflow, PlanningRequest
from stem_sci.core.enums import ProjectStage


def _advance_all(workflow: LangGraphWorkflow, project_id: str) -> dict[str, object]:
    state = workflow.start(PlanningRequest(project_id=project_id, research_intent="scope"))
    seen = [state["selected_agent"]]
    for _ in range(6):
        state = workflow.resume(project_id, decision="approved", decided_by="local-reviewer")
        if "__interrupt__" not in state:
            break
        seen.append(state["selected_agent"])
    assert seen == [
        "mentor_planning",
        "evidence_review",
        "research_design",
        "data_analysis",
        "paper_writing",
        "independent_review",
    ]
    return state


def test_langgraph_pauses_and_completes_six_agent_chain() -> None:
    workflow = LangGraphWorkflow()
    first = workflow.start(PlanningRequest(project_id="graph-six", research_intent="scope"))

    assert first["current_stage"] == ProjectStage.WAITING_HUMAN.value
    assert first["__interrupt__"][0].value["agent_id"] == "mentor_planning"  # type: ignore[index]

    final = _advance_all(workflow, "graph-six")

    assert final["final_stage"] == ProjectStage.VERIFIED.value
    assert final["agent_chain_complete"] is True
    assert final["validated_result_available"] is False
    assert final["workflow_status"] == "AGENT_CHAIN_COMPLETE_REQUIRES_DATA_VALIDATION"


def test_langgraph_rejection_routes_to_rework_agent() -> None:
    workflow = LangGraphWorkflow()
    project_id = "graph-rework"
    workflow.start(PlanningRequest(project_id=project_id, research_intent="scope"))

    evidence_state = workflow.resume(project_id, decision="approved", decided_by="local")
    assert evidence_state["selected_agent"] == "evidence_review"

    rework_state = workflow.resume(project_id, decision="rejected", decided_by="local")
    assert rework_state["selected_agent"] == "evidence_review"
    assert rework_state["current_stage"] == ProjectStage.WAITING_HUMAN.value
    assert rework_state["__interrupt__"]  # type: ignore[truthy-bool]


def test_langgraph_rejects_invalid_resume_payload() -> None:
    workflow = LangGraphWorkflow()
    project_id = "graph-invalid"
    workflow.start(PlanningRequest(project_id=project_id, research_intent="scope"))

    with pytest.raises(ValueError, match="approved or rejected"):
        workflow.graph.invoke(
            Command(resume={"decision": "maybe"}),
            {"configurable": {"thread_id": project_id}},
        )

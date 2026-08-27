from __future__ import annotations

import pytest

from stem_sci.controller import PlanningRequest, ResearchController
from stem_sci.controller.workflow_timeline import (
    InMemoryWorkflowFeedbackStore,
    WorkflowFeedback,
    WorkflowFeedbackAction,
)


def test_feedback_rerun_rejects_candidate_and_reruns_same_agent() -> None:
    controller = ResearchController(feedback_store=InMemoryWorkflowFeedbackStore())
    controller.start_planning(
        PlanningRequest(
            project_id="feedback-rerun",
            research_intent="physics STEM",
            run_id="planning-1",
        )
    )

    result = controller.apply_workflow_feedback(
        WorkflowFeedback(
            feedback_id="feedback-1",
            project_id="feedback-rerun",
            agent_id="mentor_planning",
            stage="WAITING_HUMAN",
            action=WorkflowFeedbackAction.RERUN,
            feedback="将对象限制为师范生",
            created_by="researcher",
        )
    )

    assert result.workflow_run is not None
    assert result.workflow_run.route_decision.selected_route == "mentor_planning"
    assert "师范生" in controller.workflow_timeline("feedback-rerun").research_intent


def test_feedback_continue_stops_at_pending_approval() -> None:
    controller = ResearchController(feedback_store=InMemoryWorkflowFeedbackStore())
    controller.start_planning(PlanningRequest(project_id="feedback-gate", research_intent="scope"))

    with pytest.raises(ValueError, match="pending approval"):
        controller.apply_workflow_feedback(
            WorkflowFeedback(
                feedback_id="feedback-2",
                project_id="feedback-gate",
                agent_id="mentor_planning",
                stage="WAITING_HUMAN",
                action=WorkflowFeedbackAction.CONTINUE,
                feedback="继续",
                created_by="researcher",
            )
        )

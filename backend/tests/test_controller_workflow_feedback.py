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


def test_repeated_identical_feedback_is_not_appended_to_research_intent() -> None:
    controller = ResearchController(feedback_store=InMemoryWorkflowFeedbackStore())
    controller.start_planning(PlanningRequest(project_id="feedback-dedupe", research_intent="scope"))
    feedback = "检索目标：验证干预效果；文献范围：2020-2026；证据来源：平台知识库"

    for index in range(2):
        controller.apply_workflow_feedback(
            WorkflowFeedback(
                feedback_id=f"feedback-dedupe-{index}",
                project_id="feedback-dedupe",
                agent_id="mentor_planning",
                stage="WAITING_HUMAN",
                action=WorkflowFeedbackAction.RERUN,
                feedback=feedback,
                created_by="researcher",
            )
        )

    intent = controller.workflow_timeline("feedback-dedupe").research_intent
    assert intent.count(f"[User feedback for mentor_planning]: {feedback}") == 1


def test_conversation_context_is_used_by_rerun_candidate() -> None:
    controller = ResearchController(feedback_store=InMemoryWorkflowFeedbackStore())
    controller.start_planning(
        PlanningRequest(project_id="conversation-sync", research_intent="Python physics")
    )

    controller.update_conversation_context(
        "conversation-sync",
        "mentor_planning",
        {
            "population": "大一物理师范生",
            "context": "大学物理实验室",
            "intervention": "分层AI支架",
            "comparator": "常规提示",
            "primary_outcome": "迁移得分",
        },
    )
    result = controller.apply_workflow_feedback(
        WorkflowFeedback(
            feedback_id="conversation-sync-rerun",
            project_id="conversation-sync",
            agent_id="mentor_planning",
            stage="WAITING_HUMAN",
            action=WorkflowFeedbackAction.RERUN,
            feedback="基于会话状态重新生成候选",
            created_by="researcher",
        )
    )

    assert result.workflow_run is not None
    body = controller._latest_artifact_body(
        "conversation-sync", "mentor_planning", "ResearchContractCandidate"
    )
    assert body["population"] == "大一物理师范生"
    assert body["context"] == "大学物理实验室"
    assert body["intervention"] == "分层AI支架"
    assert body["comparator"] == "常规提示"
    assert body["outcomes"] == ["迁移得分"]


def test_llm_planning_enrichment_does_not_overwrite_confirmed_fields() -> None:
    from stem_sci.agents.planner import MentorPlanningAgent
    from stem_sci.agents.research_generation import PlanningBriefCandidate
    from stem_sci.agents.runtime import FakeLLMProvider, StructuredGenerator

    generator = StructuredGenerator(
        FakeLLMProvider(
            [
                {
                    "population": "目标研究人群（待确认）",
                    "context": "教育或科研应用场景（待确认）",
                    "intervention": "研究意图中描述的干预、方法或技术",
                    "comparator": "常规方法或基线条件（待确认）",
                    "primary_outcome": "主要研究目标指标（待确认）",
                    "clarifying_questions": [],
                }
            ]
        )
    )
    planner = MentorPlanningAgent(
        pipeline=__import__("stem_sci.agents.research_generation", fromlist=["MentorPlanningPipeline"]).MentorPlanningPipeline(
            generator=generator, model="test-model"
        )
    )
    brief = controller_brief = ResearchController()._build_planning_brief(
        "p", __import__("stem_sci.agents", fromlist=["AgentInput"]).AgentInput(
            agent_run_id="r", task_ref="p:planning", context_bundle_ref="context://initial",
            policy_version="v1", prompt_template_version="v1"
        ),
        "研究对象：大一物理师范生；研究场景：大学物理实验室；干预：分层AI支架；对照：常规提示；主要指标：迁移得分",
    )
    enriched = ResearchController._llm_enrich_planning_brief(planner, controller_brief, "confirmed")
    assert enriched.population == "大一物理师范生"
    assert enriched.context == "大学物理实验室"
    assert enriched.intervention == "分层AI支架"
    assert enriched.comparator == "常规提示"
    assert enriched.candidate_outcomes == ["迁移得分"]

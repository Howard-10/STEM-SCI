import pytest

from stem_sci.agents.contracts import ReviewFinding
from stem_sci.context.models import ContextBundle
from stem_sci.controller import PlanningRequest, ResearchController
from stem_sci.core.enums import DecisionScope, ProjectStage


def test_rejected_evidence_approval_routes_back_to_evidence_agent() -> None:
    controller = ResearchController()
    planning = controller.start_planning(
        PlanningRequest(
            project_id="rework-evidence-demo",
            research_intent="研究 Python 物理建模迁移能力",
            run_id="rework-planning-1",
        )
    )
    controller.resume_approval(
        "rework-evidence-demo",
        planning.approval_request,
        decision="approved",
        decided_by="researcher",
    )
    evidence = controller.run_next("rework-evidence-demo")

    rejected = controller.resume_approval(
        "rework-evidence-demo",
        evidence.approval_request,
        decision="rejected",
        decided_by="researcher",
    )

    assert rejected.current_stage is ProjectStage.REWORK
    assert rejected.rework_target_agent == "evidence_review"
    assert rejected.rework_reason == "evidence_protocol approval was rejected"

    rework = controller.run_next("rework-evidence-demo")

    assert rework.route_decision.selected_route == "evidence_review"
    assert rework.route_decision.current_stage is ProjectStage.REWORK
    assert rework.approval_request.approval_type == "evidence_protocol"
    assert rework.workflow_state.current_stage is ProjectStage.WAITING_HUMAN


def test_approved_rework_clears_rework_target() -> None:
    controller = ResearchController()
    planning = controller.start_planning(
        PlanningRequest(project_id="rework-clear-demo", research_intent="scope", run_id="clear-1")
    )
    controller.resume_approval(
        "rework-clear-demo",
        planning.approval_request,
        decision="approved",
        decided_by="researcher",
    )
    evidence = controller.run_next("rework-clear-demo")
    controller.resume_approval(
        "rework-clear-demo",
        evidence.approval_request,
        decision="rejected",
        decided_by="researcher",
    )
    rework = controller.run_next("rework-clear-demo")
    approved = controller.resume_approval(
        "rework-clear-demo",
        rework.approval_request,
        decision="approved",
        decided_by="researcher",
    )

    assert approved.current_stage is ProjectStage.EVIDENCE_READY
    assert approved.rework_target_agent is None


def test_incomplete_evidence_cannot_be_approved() -> None:
    class EmptyFormalContextProvider:
        def build_context(
            self, project_id: str, task_ref: str, query: str, token_budget: int
        ) -> ContextBundle:
            return ContextBundle(
                context_id="empty-formal-context",
                project_id=project_id,
                task_ref=task_ref,
                query=query,
                evidence_refs=[],
                source_refs=[],
                risk_flags=["INSUFFICIENT_CORPUS_COVERAGE"],
                verification_summary={},
                token_budget=token_budget,
                estimated_tokens=0,
                context_hash="e" * 64,
                generated_at="2026-08-21T00:00:00Z",
            )

    controller = ResearchController(context_provider=EmptyFormalContextProvider())
    project_id = "blocked-evidence-approval"
    planning = controller.start_planning(
        PlanningRequest(project_id=project_id, research_intent="scope", run_id="blocked-1")
    )
    controller.resume_approval(project_id, planning.approval_request, decision="approved", decided_by="r")
    evidence = controller.run_next(project_id)

    with pytest.raises(ValueError, match="verified evidence is required"):
        controller.resume_approval(
            project_id, evidence.approval_request, decision="approved", decided_by="r"
        )

    state = controller.get_state(project_id)
    assert state.current_stage is ProjectStage.WAITING_HUMAN
    assert state.pending_approval_ref == evidence.approval_request.request_id

    rejected = controller.resume_approval(
        project_id, evidence.approval_request, decision="rejected", decided_by="r"
    )
    assert rejected.current_stage is ProjectStage.REWORK
    assert rejected.rework_target_agent == "evidence_review"


def test_full_six_agent_path_routes_review_rework_to_paper_writing() -> None:
    controller = ResearchController()
    project_id = "full-path-demo"
    planning = controller.start_planning(
        PlanningRequest(project_id=project_id, research_intent="scope", run_id="full-path-1")
    )
    controller.resume_approval(project_id, planning.approval_request, decision="approved", decided_by="r")

    evidence = controller.run_next(project_id)
    controller.resume_approval(project_id, evidence.approval_request, decision="approved", decided_by="r")
    design = controller.run_next(project_id)
    controller.resume_approval(project_id, design.approval_request, decision="approved", decided_by="r")
    analysis = controller.run_next(project_id)
    controller.resume_approval(project_id, analysis.approval_request, decision="approved", decided_by="r")
    writing = controller.run_next(project_id)
    controller.resume_approval(project_id, writing.approval_request, decision="approved", decided_by="r")
    review = controller.run_next(project_id)
    rejected = controller.resume_approval(
        project_id, review.approval_request, decision="rejected", decided_by="r"
    )

    assert review.route_decision.selected_route == "independent_review"
    assert rejected.current_stage is ProjectStage.REWORK
    assert rejected.rework_target_agent == "paper_writing"
    assert controller.run_next(project_id).route_decision.selected_route == "paper_writing"


def test_review_method_finding_routes_rework_to_research_design() -> None:
    controller = ResearchController()
    project_id = "review-finding-demo"
    planning = controller.start_planning(
        PlanningRequest(project_id=project_id, research_intent="scope", run_id="finding-1")
    )
    controller.resume_approval(project_id, planning.approval_request, decision="approved", decided_by="r")
    evidence = controller.run_next(project_id)
    controller.resume_approval(project_id, evidence.approval_request, decision="approved", decided_by="r")
    design = controller.run_next(project_id)
    controller.resume_approval(project_id, design.approval_request, decision="approved", decided_by="r")
    analysis = controller.run_next(project_id)
    controller.resume_approval(project_id, analysis.approval_request, decision="approved", decided_by="r")
    writing = controller.run_next(project_id)
    controller.resume_approval(project_id, writing.approval_request, decision="approved", decided_by="r")
    review = controller.run_next(project_id)
    controller.resume_approval(project_id, review.approval_request, decision="rejected", decided_by="r")

    rerouted = controller.route_review_finding(
        project_id,
        ReviewFinding(
            finding_id="finding-method-1",
            reviewer_type="method_reviewer",
            artifact_ref=review.approval_request.artifact_ref,
            severity="major",
            category="method",
            description="Estimand and assignment logic are not aligned.",
            suggested_action="Return to research design.",
            blocked_target_ids=["protocol://review-finding-demo/v1"],
        ),
    )

    assert rerouted.rework_target_agent == "research_design"
    assert rerouted.rework_trigger_refs == ["finding-method-1"]
    assert rerouted.rework_target_refs == ["protocol://review-finding-demo/v1"]
    assert "Estimand" in (rerouted.rework_reason or "")
    assert controller.run_next(project_id).route_decision.selected_route == "research_design"


def test_stage_scoped_review_finding_blocks_the_controller_stage() -> None:
    controller = ResearchController()
    project_id = "review-stage-block-demo"
    planning = controller.start_planning(
        PlanningRequest(project_id=project_id, research_intent="scope", run_id="stage-block-1")
    )
    controller.resume_approval(project_id, planning.approval_request, decision="approved", decided_by="r")
    evidence = controller.run_next(project_id)
    controller.resume_approval(project_id, evidence.approval_request, decision="approved", decided_by="r")
    design = controller.run_next(project_id)
    controller.resume_approval(project_id, design.approval_request, decision="approved", decided_by="r")
    analysis = controller.run_next(project_id)
    controller.resume_approval(project_id, analysis.approval_request, decision="approved", decided_by="r")
    writing = controller.run_next(project_id)
    controller.resume_approval(project_id, writing.approval_request, decision="approved", decided_by="r")
    review = controller.run_next(project_id)
    controller.resume_approval(project_id, review.approval_request, decision="rejected", decided_by="r")

    blocked = controller.route_review_finding(
        project_id,
        ReviewFinding(
            finding_id="finding-stage-1",
            reviewer_type="pedagogy",
            artifact_ref="protocol://review-stage-block-demo/v1",
            severity="critical",
            category="pedagogy",
            description="Transfer task does not measure unaided transfer.",
            suggested_action="Redesign the study before analysis continues.",
            decision_scope=DecisionScope.STAGE,
            blocked_target_ids=["stage://analysis"],
        ),
    )

    assert blocked.current_stage is ProjectStage.BLOCKED
    assert blocked.rework_target_refs == ["stage://analysis"]
    assert controller.get_state(project_id).current_stage is ProjectStage.BLOCKED

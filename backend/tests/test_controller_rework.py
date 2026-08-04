from stem_sci.agents.contracts import ReviewFinding
from stem_sci.controller import PlanningRequest, ResearchController
from stem_sci.core.enums import ProjectStage


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
        ),
    )

    assert rerouted.rework_target_agent == "research_design"
    assert rerouted.rework_trigger_refs == ["finding-method-1"]
    assert "Estimand" in (rerouted.rework_reason or "")
    assert controller.run_next(project_id).route_decision.selected_route == "research_design"

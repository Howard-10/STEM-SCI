from stem_sci.controller import PlanningRequest, ResearchController
from stem_sci.core.enums import ProjectStage


def test_approval_resume_is_idempotent() -> None:
    controller = ResearchController()
    run = controller.start_planning(PlanningRequest(project_id="idempotent", research_intent="scope"))
    first = controller.resume_approval("idempotent", run.approval_request, decision="approved", decided_by="r")
    second = controller.resume_approval("idempotent", run.approval_request, decision="approved", decided_by="r")
    assert first == second
    assert first.current_stage is ProjectStage.SCOPED

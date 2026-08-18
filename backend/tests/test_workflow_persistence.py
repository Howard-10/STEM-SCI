from datetime import UTC, datetime

import pytest

from stem_sci.controller import (
    PlanningRequest,
    ResearchController,
    SQLiteDecisionStore,
    SQLiteWorkflowStore,
)
from stem_sci.core.enums import ProjectStage
from stem_sci.core.models import ApprovalRecord


def test_controller_restores_waiting_workflow_and_resumes_idempotently(tmp_path) -> None:
    database = tmp_path / "workflow.db"
    first_controller = ResearchController(
        workflow_store=SQLiteWorkflowStore(database),
        decision_store=SQLiteDecisionStore(database),
    )
    first = first_controller.start_planning(
        PlanningRequest(
            project_id="persistent-demo",
            research_intent="研究 Python 物理建模迁移能力",
            run_id="persistent-planning",
        )
    )

    restarted_controller = ResearchController(
        workflow_store=SQLiteWorkflowStore(database),
        decision_store=SQLiteDecisionStore(database),
    )
    restored = restarted_controller.get_state("persistent-demo")

    assert restored.current_stage is ProjectStage.WAITING_HUMAN
    assert restored.pending_approval_ref == first.approval_request.request_id
    assert restored.research_state is not None
    assert restored.research_state.project_id == "persistent-demo"

    resumed = restarted_controller.resume_approval(
        "persistent-demo",
        restarted_controller.get_pending_approval("persistent-demo"),
        decision="approved",
        decided_by="researcher",
    )
    repeated = restarted_controller.resume_approval(
        "persistent-demo",
        first.approval_request,
        decision="approved",
        decided_by="researcher",
    )

    assert resumed.current_stage is ProjectStage.SCOPED
    assert repeated == resumed


def test_sqlite_decision_store_rejects_cross_approval_idempotency_reuse(tmp_path) -> None:
    database = tmp_path / "workflow.db"
    store = SQLiteDecisionStore(database)
    base = {
        "project_id": "decision-demo",
        "artifact_id": "artifact-1",
        "artifact_version": 1,
        "decision": "approved",
        "decided_by": "researcher",
        "decided_at": datetime.now(UTC),
        "reason": "scope",
        "idempotency_key": "same-key",
    }
    store.put(ApprovalRecord(approval_id="approval-1", **base))
    with pytest.raises(ValueError, match="idempotency key"):
        store.put(ApprovalRecord(approval_id="approval-2", **base))


def test_controller_replays_durable_decision_when_snapshot_is_still_pending(tmp_path) -> None:
    database = tmp_path / "workflow.db"
    controller = ResearchController(
        workflow_store=SQLiteWorkflowStore(database),
        decision_store=SQLiteDecisionStore(database),
    )
    first = controller.start_planning(
        PlanningRequest(project_id="replay-demo", research_intent="scope", run_id="replay-1")
    )
    controller.decision_store.put(
        ApprovalRecord(
            approval_id=first.approval_request.request_id,
            project_id="replay-demo",
            artifact_id=first.approval_request.artifact_ref,
            artifact_version=1,
            decision="approved",
            decided_by="recovery-test",
            decided_at=datetime.now(UTC),
            reason=first.approval_request.reason,
            idempotency_key=f"resume:{first.approval_request.request_id}:approved",
        )
    )

    restarted = ResearchController(
        workflow_store=SQLiteWorkflowStore(database),
        decision_store=SQLiteDecisionStore(database),
    )
    resumed = restarted.resume_approval(
        "replay-demo",
        first.approval_request,
        decision="approved",
        decided_by="recovery-test",
    )

    assert resumed.current_stage is ProjectStage.SCOPED


def test_direct_planning_approval_does_not_restore_stale_pending_request(tmp_path) -> None:
    database = tmp_path / "workflow.db"
    controller = ResearchController(workflow_store=SQLiteWorkflowStore(database))
    first = controller.start_planning(
        PlanningRequest(project_id="direct-demo", research_intent="scope", run_id="direct-1")
    )
    controller.approve_planning(first.workflow_state, first.approval_request)

    restarted = ResearchController(workflow_store=SQLiteWorkflowStore(database))

    assert restarted.get_state("direct-demo").current_stage is ProjectStage.SCOPED
    with pytest.raises(ValueError, match="no pending approval"):
        restarted.get_pending_approval("direct-demo")

from datetime import UTC, datetime

from stem_sci.controller.gates.models import GateResult
from stem_sci.core.enums import DecisionScope, GateDecision


def test_gate_result_preserves_decision_scope_and_blocked_targets() -> None:
    gate = GateResult(
        gate_id="gate-1", gate_version="v1", project_id="scope-demo", artifact_id="artifact-1",
        decision=GateDecision.BLOCKED, decision_scope=DecisionScope.TASK,
        blocked_target_ids=["task://analysis"], next_action="return to analysis",
        created_at=datetime.now(UTC)
    )
    assert gate.decision_scope is DecisionScope.TASK
    assert gate.blocked_target_ids == ["task://analysis"]

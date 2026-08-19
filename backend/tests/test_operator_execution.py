from stem_sci.agents import ToolRequest
from stem_sci.artifacts.execution_store import SQLiteExecutionStore
from stem_sci.controller import OperatorExecutor, PlanningRequest, ResearchController
from stem_sci.core.enums import ProjectStage, RunStatus
from stem_sci.operators.registry import OperatorRegistry


def test_registered_but_unimplemented_operator_is_recorded_as_blocked() -> None:
    executor = OperatorExecutor(OperatorRegistry.default())

    runs = executor.execute_tool_requests(
        project_id="operator-demo",
        agent_run_id="agent-run-1",
        tool_requests=["request://literature_search"],
    )

    assert len(runs) == 1
    assert runs[0].operator_id == "literature_search"
    assert runs[0].status is RunStatus.BLOCKED
    assert runs[0].error_ref == "error://operator/literature_search/unsupported"


def test_unknown_operator_request_is_recorded_as_failed() -> None:
    executor = OperatorExecutor(OperatorRegistry.default())

    runs = executor.execute_tool_requests(
        project_id="operator-demo",
        agent_run_id="agent-run-2",
        tool_requests=["request://does_not_exist"],
    )

    assert runs[0].status is RunStatus.FAILED
    assert runs[0].error_ref == "error://operator/does_not_exist/unknown"


def test_operator_executor_accepts_structured_tool_request() -> None:
    executor = OperatorExecutor(OperatorRegistry.default())
    run = executor.execute(
        "operator-structured-demo",
        ToolRequest(
            request_id="structured-tool-1",
            capability="literature_search",
            input_refs=["artifact://scope/1"],
            required_output_types=["EvidenceSet"],
            reason="Need evidence.",
        ),
    )

    assert run.request_ref == "structured-tool-1"
    assert run.input_artifact_refs == ["artifact://scope/1"]


def test_sqlite_execution_store_restores_operator_run(tmp_path) -> None:
    database = tmp_path / "workflow.db"
    executor = OperatorExecutor(
        OperatorRegistry.default(), SQLiteExecutionStore(database)
    )
    run = executor.execute_tool_requests(
        project_id="operator-persist-demo",
        agent_run_id="agent-run-3",
        tool_requests=["request://literature_search"],
    )[0]

    restored = SQLiteExecutionStore(database).get("operator-persist-demo", run.operator_run_id)

    assert restored == run


def test_controller_does_not_downgrade_versioned_tools_to_legacy_operators() -> None:
    controller = ResearchController(
        operator_executor=OperatorExecutor(OperatorRegistry.default())
    )
    first = controller.start_planning(
        PlanningRequest(
            project_id="operator-controller-demo",
            research_intent="scope",
            run_id="operator-planning-1",
        )
    )
    scoped = controller.approve_planning(first.workflow_state, first.approval_request)
    next_run = controller.run_next("operator-controller-demo")

    assert scoped.current_stage is ProjectStage.SCOPED
    state = next_run.workflow_state.research_state
    assert state is not None
    assert state.execution_run_refs == []
    assert "TOOL_EXECUTOR_UNAVAILABLE" in state.risk_flags

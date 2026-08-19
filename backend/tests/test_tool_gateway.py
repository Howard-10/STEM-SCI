from stem_sci.agents.contracts import ToolRequest
from stem_sci.artifacts.artifact_store import InMemoryArtifactStore
from stem_sci.artifacts.content_store import InMemoryArtifactContentStore
from stem_sci.artifacts.decision_store import InMemoryDecisionStore
from stem_sci.controller.budget.budget_manager import BudgetManager, BudgetState
from stem_sci.tools.gateway import ToolGateway
from stem_sci.tools.models import ToolExecutionMode, ToolResult, ToolRunStatus, ToolSpec
from stem_sci.tools.registry import ToolRegistry


def _spec(tool_id: str, mode: ToolExecutionMode = ToolExecutionMode.READ_ONLY) -> ToolSpec:
    return ToolSpec(
        tool_id=tool_id,
        tool_version="v1",
        capability=tool_id,
        execution_mode=mode,
        input_schema_ref="schema://Input",
        output_schema_ref="schema://Output",
        timeout_seconds=10,
    )


class FakeExecutor:
    def execute(self, spec, project_id, agent_id, agent_run_id, request):
        return ToolResult(
            tool_run_id="executor-run",
            project_id=project_id,
            tool_id=spec.tool_id,
            tool_version=spec.tool_version,
            status=ToolRunStatus.SUCCEEDED,
            output_payloads=[
                {
                    "artifact_type": "ToolCandidate",
                    "schema_version": "v1",
                    "body": {"ok": True},
                }
            ],
        )


def _gateway(spec: ToolSpec, *, decision_store=None) -> ToolGateway:
    return ToolGateway(
        tool_registry=ToolRegistry([spec]),
        executor=FakeExecutor(),
        decision_store=decision_store,
        artifact_store=InMemoryArtifactStore(),
        artifact_content_store=InMemoryArtifactContentStore(),
    )


def test_gateway_rejects_cross_project_input() -> None:
    gateway = _gateway(_spec("knowledge_base_search"))
    result = gateway.execute(
        project_id="project-a",
        agent_id="evidence_review",
        agent_run_id="run-1",
        request=ToolRequest(
            request_id="request-1",
            capability="knowledge_base_search",
            input_refs=["artifact://project-b/source-1"],
            reason="read evidence",
        ),
    )
    assert result.status is ToolRunStatus.BLOCKED
    assert result.error_code == "PROJECT_SCOPE_VIOLATION"


def test_gateway_blocks_controlled_write_without_approval() -> None:
    gateway = _gateway(
        _spec("candidate_writer", ToolExecutionMode.CONTROLLED_WRITE),
        decision_store=InMemoryDecisionStore(),
    )
    result = gateway.execute(
        project_id="project-a",
        agent_id="data_analysis",
        agent_run_id="run-1",
        request=ToolRequest(
            request_id="request-1", capability="candidate_writer", reason="write"
        ),
    )
    assert result.status is ToolRunStatus.BLOCKED
    assert result.error_code == "APPROVAL_REQUIRED"


def test_gateway_persists_successful_candidate_output() -> None:
    contents = InMemoryArtifactContentStore()
    gateway = ToolGateway(
        tool_registry=ToolRegistry([_spec("candidate_writer", ToolExecutionMode.CANDIDATE_OUTPUT)]),
        executor=FakeExecutor(),
        artifact_content_store=contents,
    )
    result = gateway.execute(
        project_id="project-a",
        agent_id="evidence_review",
        agent_run_id="run-1",
        request=ToolRequest(
            request_id="request-1", capability="candidate_writer", reason="candidate"
        ),
    )
    assert result.status is ToolRunStatus.SUCCEEDED
    assert contents.list_project("project-a")


def test_gateway_consumes_budget_only_for_model_backed_tools() -> None:
    budget = BudgetManager(BudgetState(max_llm_calls=1))
    gateway = ToolGateway(
        tool_registry=ToolRegistry([_spec("model_tool")]),
        executor=FakeExecutor(),
        budget_manager=budget,
        model_backed_tool_ids=["model_tool"],
    )
    request = ToolRequest(request_id="request-1", capability="model_tool", reason="model")
    assert gateway.execute(
        project_id="project-a", agent_id="evidence_review", agent_run_id="run-1", request=request
    ).status is ToolRunStatus.SUCCEEDED
    assert budget.state.used_llm_calls == 1


from stem_sci.agents.contracts import ToolRequest
from stem_sci.tools.gateway import ToolGateway
from stem_sci.tools.models import ToolExecutionMode, ToolResult, ToolRunStatus, ToolSpec
from stem_sci.tools.registry import ToolRegistry


class SecretExecutor:
    def execute(self, spec, project_id, agent_id, agent_run_id, request):
        return ToolResult(
            tool_run_id="secret-run",
            project_id=project_id,
            tool_id=spec.tool_id,
            tool_version=spec.tool_version,
            status=ToolRunStatus.FAILED,
            error_code="secret-sentinel prompt-sentinel",
            risk_flags=["secret-sentinel", "prompt-sentinel"],
        )


def test_tool_audit_redacts_raw_error_and_risk_strings() -> None:
    spec = ToolSpec(
        tool_id="secret_test",
        tool_version="v1",
        capability="secret_test",
        execution_mode=ToolExecutionMode.READ_ONLY,
        input_schema_ref="schema://Input",
        output_schema_ref="schema://Output",
        timeout_seconds=10,
    )
    gateway = ToolGateway(tool_registry=ToolRegistry([spec]), executor=SecretExecutor())
    result = gateway.execute(
        project_id="project-a",
        agent_id="evidence_review",
        agent_run_id="run-1",
        request=ToolRequest(request_id="request-1", capability="secret_test@v1", reason="sentinel"),
    )
    record = gateway.tool_run_store.list_project("project-a")[0]
    assert "secret-sentinel" not in result.error_code
    assert "prompt-sentinel" not in result.error_code
    assert record.error_code == "EXECUTION_FAILED"
    assert record.risk_flags == []

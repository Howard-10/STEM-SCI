from stem_sci.agents.contracts import ToolRequest
from stem_sci.api import workflow_controller
from stem_sci.tools import ToolRunStatus


def test_default_controller_exposes_all_six_agent_boundaries() -> None:
    capabilities = workflow_controller.list_agent_capabilities()
    assert {item.agent_id for item in capabilities} == {
        "mentor_planning",
        "evidence_review",
        "research_design",
        "data_analysis",
        "paper_writing",
        "independent_review",
    }
    assert all(item.skill_ids and item.tool_ids for item in capabilities)


def test_unavailable_default_executor_is_typed_and_audited() -> None:
    result = workflow_controller.tool_gateway.execute(
        project_id="fake-project",
        agent_id="evidence_review",
        agent_run_id="fake-run",
        request=ToolRequest(
            request_id="fake-request",
            capability="knowledge_base_search@v1",
            reason="offline fake tool boundary",
        ),
    )
    assert result.status is ToolRunStatus.BLOCKED
    assert result.error_code == "TOOL_EXECUTOR_UNAVAILABLE"
    assert workflow_controller.tool_gateway.tool_run_store.list_project("fake-project")

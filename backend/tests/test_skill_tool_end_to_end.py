from uuid import uuid4

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


def test_default_executor_runs_and_audits_local_tool() -> None:
    result = workflow_controller.tool_gateway.execute(
        project_id="fake-project-execution",
        agent_id="evidence_review",
        agent_run_id="fake-run",
        request=ToolRequest(
            request_id=f"fake-request-execution-{uuid4().hex}",
            capability="knowledge_base_search@v1",
            input_payload={"query": "physics", "limit": 10},
            reason="offline fake tool boundary",
        ),
    )
    assert result.status is ToolRunStatus.SUCCEEDED
    assert result.output_data is not None
    assert workflow_controller.tool_gateway.tool_run_store.list_project("fake-project-execution")

from uuid import uuid4

from fastapi.testclient import TestClient

from stem_sci.api import app

client = TestClient(app)
PROJECT_ID = f"api-physics-demo-{uuid4().hex[:8]}"
PLANNING_RUN_ID = f"api-planning-{uuid4().hex[:8]}"


def test_workflow_api_exposes_planning_and_next_route() -> None:
    response = client.post(
        "/api/v1/workflow/projects",
        json={
            "project_id": PROJECT_ID,
            "research_intent": "研究分层 AI 支架对 Python 物理建模迁移能力的影响",
            "run_id": PLANNING_RUN_ID,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow_state"]["current_stage"] == "WAITING_HUMAN"
    assert payload["approval_request"]["approval_type"] == "research_scope"
    assert payload["agent_result"]["tool_requests"]
    assert {
        request["capability"] for request in payload["agent_result"]["tool_requests"]
    } == {"research_scope_validator@v1"}
    assert payload["route_decision"]["required_tools"] == [
        "context_bundle_read@v1",
        "research_scope_validator@v1",
    ]

    approval = client.post(
        f"/api/v1/workflow/projects/{PROJECT_ID}/approve",
        json={"decision": "approved", "decided_by": "researcher"},
    )
    assert approval.status_code == 200
    assert approval.json()["current_stage"] == "SCOPED"

    next_run = client.post(f"/api/v1/workflow/projects/{PROJECT_ID}/next")
    assert next_run.status_code == 200
    assert next_run.json()["route_decision"]["selected_route"] == "evidence_review"
    assert {
        request["capability"]
        for request in next_run.json()["agent_result"]["tool_requests"]
    } == {"context_bundle_read@v1", "knowledge_base_search@v1"}

    tool_runs = client.get(f"/api/v1/workflow/projects/{PROJECT_ID}/tool-runs")
    assert tool_runs.status_code == 200
    project_runs = tool_runs.json()
    assert project_runs
    assert {run["agent_id"] for run in project_runs} >= {
        "mentor_planning",
        "evidence_review",
    }
    assert all(run["project_id"] == PROJECT_ID for run in project_runs)
    current_agent_runs = {
        payload["agent_result"]["agent_run_id"],
        next_run.json()["agent_result"]["agent_run_id"],
    }
    current_tool_runs = [
        run for run in project_runs if run["agent_run_id"] in current_agent_runs
    ]
    assert current_tool_runs
    assert all(run["status"] == "SUCCEEDED" for run in current_tool_runs)
    assert any(
        run["agent_id"] == "mentor_planning" and run["output_content_refs"]
        for run in current_tool_runs
    )

    rejected = client.post(
        f"/api/v1/workflow/projects/{PROJECT_ID}/approve",
        json={"decision": "rejected", "decided_by": "researcher"},
    )
    assert rejected.status_code == 200
    finding = client.post(
        f"/api/v1/workflow/projects/{PROJECT_ID}/review-findings",
        json={
            "finding_id": "api-method-finding",
            "reviewer_type": "method_reviewer",
            "artifact_ref": next_run.json()["approval_request"]["artifact_ref"],
            "severity": "major",
            "category": "method",
            "description": "The protocol needs a clearer estimand.",
            "suggested_action": "Return to research design.",
        },
    )
    assert finding.status_code == 200
    assert finding.json()["rework_target_agent"] == "research_design"


def test_workflow_api_lists_capabilities() -> None:
    response = client.get("/api/v1/workflow/agents")

    assert response.status_code == 200
    assert {item["agent_id"] for item in response.json()} == {
        "mentor_planning",
        "evidence_review",
        "research_design",
        "data_analysis",
        "paper_writing",
        "independent_review",
    }


def test_workflow_api_exposes_legacy_operator_audit_endpoint() -> None:
    response = client.get("/api/v1/workflow/projects/api-empty-operator-audit/executions")

    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert all("operator_run_id" in run for run in response.json())

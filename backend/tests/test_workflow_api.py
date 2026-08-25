from fastapi.testclient import TestClient

from stem_sci.api import app

client = TestClient(app)


def test_workflow_api_exposes_planning_and_next_route() -> None:
    response = client.post(
        "/api/v1/workflow/projects",
        json={
            "project_id": "api-physics-demo",
            "research_intent": "研究分层 AI 支架对 Python 物理建模迁移能力的影响",
            "run_id": "api-planning-1",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow_state"]["current_stage"] == "WAITING_HUMAN"
    assert payload["approval_request"]["approval_type"] == "research_scope"

    approval = client.post(
        "/api/v1/workflow/projects/api-physics-demo/approve",
        json={"decision": "approved", "decided_by": "researcher"},
    )
    assert approval.status_code == 200
    assert approval.json()["current_stage"] == "SCOPED"

    next_run = client.post("/api/v1/workflow/projects/api-physics-demo/next")
    assert next_run.status_code == 200
    assert next_run.json()["route_decision"]["selected_route"] == "evidence_review"

    blocked_approval = client.post(
        "/api/v1/workflow/projects/api-physics-demo/approve",
        json={"decision": "approved", "decided_by": "researcher"},
    )
    assert blocked_approval.status_code == 400
    assert "verified evidence is required" in blocked_approval.json()["error"]["message"]

    rejected = client.post(
        "/api/v1/workflow/projects/api-physics-demo/approve",
        json={"decision": "rejected", "decided_by": "researcher"},
    )
    assert rejected.status_code == 200
    finding = client.post(
        "/api/v1/workflow/projects/api-physics-demo/review-findings",
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


def test_workflow_api_lists_project_operator_runs() -> None:
    response = client.get("/api/v1/workflow/projects/api-physics-demo/executions")

    assert response.status_code == 200
    assert response.json()
    assert all("operator_run_id" in run for run in response.json())

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stem_sci import api
from stem_sci.accounts import IdentityService


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(api, "identity_service", IdentityService(tmp_path / "identity.db"))
    return TestClient(api.app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _project(client: TestClient) -> tuple[str, str]:
    user = client.post(
        "/api/v1/auth/register",
        json={"username": "timeline-user", "email": "timeline@example.test", "password": "research-pass-123"},
    ).json()
    token = str(user["access_token"])
    project = client.post(
        "/api/v1/projects",
        headers=_auth(token),
        json={"project_id": "timeline-project", "title": "Timeline", "research_direction": "AI physics STEM"},
    )
    assert project.status_code == 200, project.text
    return token, "timeline-project"


def test_project_timeline_returns_persisted_planning_run(client: TestClient) -> None:
    token, project_id = _project(client)
    started = client.post(
        f"/api/v1/projects/{project_id}/workflow",
        headers=_auth(token),
        json={"research_intent": "研究 AI 辅助物理建模", "run_id": "timeline-planning"},
    )
    assert started.status_code == 200, started.text

    response = client.get(f"/api/v1/projects/{project_id}/workflow/timeline", headers=_auth(token))

    assert response.status_code == 200
    assert response.json()["agent_runs"][0]["agent_id"] == "mentor_planning"


def test_project_timeline_contains_structured_mentor_planning_outputs(client: TestClient) -> None:
    token, project_id = _project(client)
    started = client.post(
        f"/api/v1/projects/{project_id}/workflow",
        headers=_auth(token),
        json={"research_intent": "研究 AI 辅助物理建模", "run_id": "structured-planning"},
    )
    assert started.status_code == 200, started.text

    timeline = client.get(
        f"/api/v1/projects/{project_id}/workflow/timeline", headers=_auth(token)
    ).json()
    artifact_types = {item["artifact_type"] for item in timeline["artifact_contents"]}
    assert {"ResearchScopeCandidate", "ResearchQuestionTree", "FeasibilityReport", "ProjectRoadmap"} <= artifact_types


def test_feedback_rerun_returns_new_current_agent_run(client: TestClient) -> None:
    token, project_id = _project(client)
    client.post(
        f"/api/v1/projects/{project_id}/workflow",
        headers=_auth(token),
        json={"research_intent": "scope", "run_id": "feedback-planning"},
    )

    response = client.post(
        f"/api/v1/projects/{project_id}/workflow/feedback",
        headers=_auth(token),
        json={
            "agent_id": "mentor_planning",
            "stage": "WAITING_HUMAN",
            "action": "rerun",
            "feedback": "限定为师范生",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["workflow_run"]["route_decision"]["selected_route"] == "mentor_planning"

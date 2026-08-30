from __future__ import annotations

from pathlib import Path
import sqlite3

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


def test_project_timeline_backfills_legacy_planner_run(client: TestClient) -> None:
    token, project_id = _project(client)
    started = client.post(
        f"/api/v1/projects/{project_id}/workflow",
        headers=_auth(token),
        json={"research_intent": "研究 AI 辅助物理建模", "run_id": "legacy-planning"},
    )
    assert started.status_code == 200, started.text
    from stem_sci import api
    with sqlite3.connect(api.workflow_database) as connection:
        connection.execute(
            "delete from workflow_artifact_contents where project_id = ?", (project_id,)
        )
    timeline = client.get(
        f"/api/v1/projects/{project_id}/workflow/timeline", headers=_auth(token)
    ).json()
    assert "ResearchQuestionTree" in {item["artifact_type"] for item in timeline["artifact_contents"]}


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


def test_agent_conversation_returns_role_bounded_missing_questions(client: TestClient) -> None:
    token, project_id = _project(client)
    response = client.post(
        f"/api/v1/projects/{project_id}/workflow/conversation",
        headers=_auth(token),
        json={
            "conversation_id": "agent-chat-1",
            "agent_id": "mentor_planning",
            "message": "研究对象：大一物理师范生；研究场景：大学物理实验室",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["agent_id"] == "mentor_planning"
    assert payload["missing_requirements"] == ["intervention", "comparator", "primary_outcome"]
    assert payload["next_action"] == "ask_user"
    assert payload["questions"]


def test_complete_conversation_updates_formal_planning_candidate(client: TestClient) -> None:
    token, project_id = _project(client)
    started = client.post(
        f"/api/v1/projects/{project_id}/workflow",
        headers=_auth(token),
        json={"research_intent": "设计 Python 物理建模实验"},
    )
    assert started.status_code == 200, started.text
    response = client.post(
        f"/api/v1/projects/{project_id}/workflow/conversation",
        headers=_auth(token),
        json={
            "conversation_id": "complete-agent-chat",
            "agent_id": "mentor_planning",
            "message": "研究对象：大一物理师范生；研究场景：大学物理实验室；干预：分层AI支架；对照：常规提示；主要指标：迁移得分",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["next_action"] == "candidate_ready"

    timeline = client.get(
        f"/api/v1/projects/{project_id}/workflow/timeline", headers=_auth(token)
    ).json()
    contract = next(
        item for item in timeline["artifact_contents"]
        if item["artifact_type"] == "ResearchContractCandidate"
    )
    assert contract["body"]["population"] == "大一物理师范生"
    assert contract["body"]["context"] == "大学物理实验室"
    assert contract["body"]["intervention"] == "分层AI支架"
    assert contract["body"]["comparator"] == "常规提示"
    assert contract["body"]["outcomes"] == ["迁移得分"]

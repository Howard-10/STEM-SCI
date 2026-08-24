"""API tests for user sessions and project ownership."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stem_sci import api
from stem_sci.accounts import IdentityService
from stem_sci.documents import DocumentService
from stem_sci.knowledge.qa_memory import ConversationMemoryStore
from stem_sci.knowledge.qa_models import QAReference


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(api, "identity_service", IdentityService(tmp_path / "identity.db"))
    monkeypatch.setattr(
        api,
        "document_service",
        DocumentService(tmp_path / "documents.db", tmp_path / "project-documents"),
    )
    return TestClient(api.app)


def _register(client: TestClient, username: str, email: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": email,
            "password": "research-pass-123",
            "display_name": username.title(),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_register_login_me_refresh_and_logout(client: TestClient) -> None:
    registered = _register(client, "alice", "alice@example.test")
    access_token = str(registered["access_token"])
    refresh_token = str(registered["refresh_token"])

    me = client.get("/api/v1/auth/me", headers=_auth(access_token))
    assert me.status_code == 200
    assert me.json()["username"] == "alice"
    assert "password" not in me.text

    login = client.post(
        "/api/v1/auth/login",
        json={"login": "alice@example.test", "password": "research-pass-123"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["email"] == "alice@example.test"

    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != access_token

    logout = client.post("/api/v1/auth/logout", headers=_auth(access_token))
    assert logout.status_code == 200
    assert client.get("/api/v1/auth/me", headers=_auth(access_token)).status_code == 401


def test_duplicate_users_and_bad_credentials_are_rejected(client: TestClient) -> None:
    _register(client, "alice", "alice@example.test")

    duplicate = client.post(
        "/api/v1/auth/register",
        json={
            "username": "alice",
            "email": "alice2@example.test",
            "password": "research-pass-123",
        },
    )
    assert duplicate.status_code == 400
    assert duplicate.json()["error"]["code"] == "user_already_exists"

    bad_login = client.post(
        "/api/v1/auth/login",
        json={"login": "alice", "password": "wrong-password"},
    )
    assert bad_login.status_code == 401
    assert bad_login.json()["error"]["code"] == "invalid_credentials"


def test_project_crud_requires_auth_and_is_project_member_scoped(client: TestClient) -> None:
    alice = _register(client, "alice", "alice@example.test")
    bob = _register(client, "bob", "bob@example.test")
    alice_token = str(alice["access_token"])
    bob_token = str(bob["access_token"])

    missing_auth = client.get("/api/v1/projects")
    assert missing_auth.status_code == 401

    created = client.post(
        "/api/v1/projects",
        headers=_auth(alice_token),
        json={
            "project_id": "alice-paper",
            "title": "AI 支架与 Python 物理建模",
            "research_direction": "研究生成式 AI 分层支架对师范生建模能力的影响",
            "abstract": "初始摘要",
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["role"] == "owner"

    alice_projects = client.get("/api/v1/projects", headers=_auth(alice_token))
    assert alice_projects.status_code == 200
    assert [item["project_id"] for item in alice_projects.json()] == ["alice-paper"]

    bob_projects = client.get("/api/v1/projects", headers=_auth(bob_token))
    assert bob_projects.status_code == 200
    assert bob_projects.json() == []
    assert client.get("/api/v1/projects/alice-paper", headers=_auth(bob_token)).status_code == 404

    patched = client.patch(
        "/api/v1/projects/alice-paper",
        headers=_auth(alice_token),
        json={"title": "更新后的论文题目", "status": "archived"},
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "更新后的论文题目"
    assert patched.json()["status"] == "archived"

    deleted = client.delete("/api/v1/projects/alice-paper", headers=_auth(alice_token))
    assert deleted.status_code == 200
    assert client.get("/api/v1/projects/alice-paper", headers=_auth(alice_token)).status_code == 404


def test_project_id_is_unique_and_not_cross_user_reusable(client: TestClient) -> None:
    alice = _register(client, "alice", "alice@example.test")
    bob = _register(client, "bob", "bob@example.test")

    first = client.post(
        "/api/v1/projects",
        headers=_auth(str(alice["access_token"])),
        json={"project_id": "shared-id", "title": "A", "research_direction": "Physics STEM"},
    )
    assert first.status_code == 200

    duplicate = client.post(
        "/api/v1/projects",
        headers=_auth(str(bob["access_token"])),
        json={"project_id": "shared-id", "title": "B", "research_direction": "Other direction"},
    )
    assert duplicate.status_code == 400
    assert duplicate.json()["error"]["code"] == "project_already_exists"


def test_project_documents_are_versioned_and_member_scoped(client: TestClient) -> None:
    alice = _register(client, "alice", "alice@example.test")
    bob = _register(client, "bob", "bob@example.test")
    alice_token = str(alice["access_token"])
    bob_token = str(bob["access_token"])
    created_project = client.post(
        "/api/v1/projects",
        headers=_auth(alice_token),
        json={"project_id": "alice-paper", "title": "Paper", "research_direction": "Physics STEM"},
    )
    assert created_project.status_code == 200

    created_document = client.post(
        "/api/v1/projects/alice-paper/documents",
        headers=_auth(alice_token),
        json={
            "title": "论文草稿",
            "document_type": "manuscript",
            "format": "markdown",
            "content": "# 初稿\n研究方向。",
            "change_note": "initial draft",
        },
    )
    assert created_document.status_code == 200, created_document.text
    document_id = created_document.json()["document_id"]
    assert created_document.json()["current_version"] == 1
    assert "content" not in created_document.text

    blocked = client.get(
        f"/api/v1/projects/alice-paper/documents/{document_id}",
        headers=_auth(bob_token),
    )
    assert blocked.status_code == 404

    version_2 = client.post(
        f"/api/v1/projects/alice-paper/documents/{document_id}/versions",
        headers=_auth(alice_token),
        json={"content": "# 二稿\n补充实验方法。", "change_note": "add method"},
    )
    assert version_2.status_code == 200, version_2.text
    assert version_2.json()["version"] == 2
    assert version_2.json()["content"].startswith("# 二稿")

    versions = client.get(
        f"/api/v1/projects/alice-paper/documents/{document_id}/versions",
        headers=_auth(alice_token),
    )
    assert versions.status_code == 200
    assert [item["version"] for item in versions.json()] == [2, 1]
    assert versions.json()[1]["content"].startswith("# 初稿")

    patched = client.patch(
        f"/api/v1/projects/alice-paper/documents/{document_id}",
        headers=_auth(alice_token),
        json={"title": "正式论文草稿"},
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "正式论文草稿"

    deleted = client.delete(
        f"/api/v1/projects/alice-paper/documents/{document_id}",
        headers=_auth(alice_token),
    )
    assert deleted.status_code == 200
    assert client.get(
        f"/api/v1/projects/alice-paper/documents/{document_id}",
        headers=_auth(alice_token),
    ).status_code == 404


def test_project_chat_rejects_project_mismatch_before_qa_execution(client: TestClient) -> None:
    alice = _register(client, "alice", "alice@example.test")
    alice_token = str(alice["access_token"])
    created_project = client.post(
        "/api/v1/projects",
        headers=_auth(alice_token),
        json={"project_id": "alice-paper", "title": "Paper", "research_direction": "Physics STEM"},
    )
    assert created_project.status_code == 200

    mismatch = client.post(
        "/api/v1/projects/alice-paper/chat/answer",
        headers=_auth(alice_token),
        json={
            "project_id": "other-paper",
            "question": "下一步怎么写？",
            "mode": "discovery",
        },
    )
    assert mismatch.status_code == 400
    assert mismatch.json()["error"]["code"] == "project_mismatch"


def test_project_conversation_history_is_authenticated_and_project_scoped(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alice = _register(client, "alice", "alice@example.test")
    bob = _register(client, "bob", "bob@example.test")
    alice_token = str(alice["access_token"])
    bob_token = str(bob["access_token"])
    created = client.post(
        "/api/v1/projects",
        headers=_auth(alice_token),
        json={"project_id": "alice-paper", "title": "Paper", "research_direction": "Physics STEM"},
    )
    assert created.status_code == 200

    memory = ConversationMemoryStore(tmp_path / "memory")
    memory.append_turn(
        conversation_id="conv-alice",
        project_id="alice-paper",
        question="研究问题是什么？",
        rewritten_query="研究问题",
        answer="先明确研究对象和结果变量。",
        route="hybrid_search",
        citations=[
            QAReference(
                paper_title="Physics paper",
                source_filename="paper.txt",
                canonical_paper_id="paper-1",
                canonical_chunk_id="chunk-1",
                chunk_index=0,
                excerpt="研究对象和结果变量。",
            )
        ],
        retrieval_trace_ref="retrieval://physics_stem_v1/trace-1",
    )

    class MemoryOnlyQA:
        def list_conversations(self, project_id: str, *, limit: int = 50):
            return memory.list_conversations(project_id, limit=limit)

        def conversation_turns(self, project_id: str, conversation_id: str, *, limit: int = 100):
            return memory.conversation_turns(
                project_id=project_id,
                conversation_id=conversation_id,
                limit=limit,
            )

    monkeypatch.setattr(api, "qa_service", MemoryOnlyQA())

    missing_auth = client.get("/api/v1/projects/alice-paper/conversations")
    assert missing_auth.status_code == 401

    conversations = client.get(
        "/api/v1/projects/alice-paper/conversations",
        headers=_auth(alice_token),
    )
    assert conversations.status_code == 200
    assert conversations.json()[0]["conversation_id"] == "conv-alice"
    assert conversations.json()[0]["turn_count"] == 1

    turns = client.get(
        "/api/v1/projects/alice-paper/conversations/conv-alice/turns",
        headers=_auth(alice_token),
    )
    assert turns.status_code == 200
    assert turns.json()[0]["question"] == "研究问题是什么？"

    blocked = client.get(
        "/api/v1/projects/alice-paper/conversations",
        headers=_auth(bob_token),
    )
    assert blocked.status_code == 404

    empty_other_conversation = client.get(
        "/api/v1/projects/alice-paper/conversations/conv-missing/turns",
        headers=_auth(alice_token),
    )
    assert empty_other_conversation.status_code == 200
    assert empty_other_conversation.json() == []


def test_project_workflow_alias_requires_project_membership(client: TestClient) -> None:
    alice = _register(client, "alice", "alice@example.test")
    bob = _register(client, "bob", "bob@example.test")
    alice_token = str(alice["access_token"])
    bob_token = str(bob["access_token"])
    created = client.post(
        "/api/v1/projects",
        headers=_auth(alice_token),
        json={"project_id": "alice-paper", "title": "Paper", "research_direction": "Physics STEM"},
    )
    assert created.status_code == 200

    missing_auth = client.get("/api/v1/projects/alice-paper/workflow")
    assert missing_auth.status_code == 401

    blocked = client.get(
        "/api/v1/projects/alice-paper/workflow",
        headers=_auth(bob_token),
    )
    assert blocked.status_code == 404

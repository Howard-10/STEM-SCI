from datetime import UTC, datetime

from stem_sci.provenance.tool_run_store import InMemoryToolRunStore, SQLiteToolRunStore
from stem_sci.tools.models import ToolRunRecord, ToolRunStatus


def _record(project_id: str, tool_run_id: str) -> ToolRunRecord:
    now = datetime.now(UTC)
    return ToolRunRecord(
        tool_run_id=tool_run_id,
        project_id=project_id,
        tool_id="context_bundle_read",
        tool_version="v1",
        status=ToolRunStatus.SUCCEEDED,
        agent_id="evidence_review",
        agent_run_id="agent-run-1",
        skill_ref="bounded_corpus_review@v1",
        request_ref="request-1",
        started_at=now,
        finished_at=now,
    )


def test_in_memory_tool_run_store_is_project_scoped() -> None:
    store = InMemoryToolRunStore()
    store.put(_record("project-a", "tool-a"))
    store.put(_record("project-b", "tool-b"))
    assert store.get("project-a", "tool-b") is None
    assert [item.tool_run_id for item in store.list_project("project-a")] == ["tool-a"]


def test_sqlite_tool_run_store_is_project_scoped(tmp_path) -> None:
    store = SQLiteToolRunStore(tmp_path / "workflow.db")
    store.put(_record("project-a", "tool-a"))
    store.put(_record("project-b", "tool-b"))
    assert store.get("project-a", "tool-b") is None
    assert [item.tool_run_id for item in store.list_project("project-a")] == ["tool-a"]


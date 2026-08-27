from __future__ import annotations

from datetime import UTC, datetime

from stem_sci.controller.workflow_timeline import (
    SQLiteWorkflowFeedbackStore,
    WorkflowFeedback,
    WorkflowFeedbackAction,
)


def test_sqlite_feedback_store_returns_project_history_in_time_order(tmp_path) -> None:
    store = SQLiteWorkflowFeedbackStore(tmp_path / "workflow.db")
    later = store.put(
        WorkflowFeedback(
            feedback_id="feedback-2",
            project_id="demo",
            agent_id="evidence_review",
            stage="WAITING_HUMAN",
            action=WorkflowFeedbackAction.RERUN,
            feedback="补充近五年中文核心期刊",
            created_by="researcher",
            created_at=datetime(2026, 8, 27, 1, 2, tzinfo=UTC),
        )
    )
    earlier = store.put(
        WorkflowFeedback(
            feedback_id="feedback-1",
            project_id="demo",
            agent_id="mentor_planning",
            stage="WAITING_HUMAN",
            action=WorkflowFeedbackAction.PAUSE,
            feedback="聚焦高中物理",
            created_by="researcher",
            created_at=datetime(2026, 8, 27, 1, 1, tzinfo=UTC),
        )
    )

    assert store.list_project("demo") == [earlier, later]

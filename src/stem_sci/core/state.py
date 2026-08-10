"""Reference-only state contracts for the research workflow.

Large evidence, datasets, code, images, and execution logs belong in dedicated stores.
The graph state carries only small control values, summaries, and stable identifiers.
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class ProjectMeta(TypedDict):
    user_id: str
    project_id: str
    thread_id: str
    run_id: str


class ResearchState(TypedDict, total=False):
    project_meta: ProjectMeta
    current_stage: str
    task_status: str
    task_ledger_ref: str
    progress_ledger_ref: str
    evidence_refs: list[str]
    artifact_refs: list[str]
    data_asset_refs: list[str]
    execution_run_refs: list[str]
    decision_refs: list[str]
    approval_request_refs: list[str]
    agent_run_refs: list[str]
    recent_message_refs: list[str]
    conversation_summary: NotRequired[dict[str, Any]]
    long_memory_refs: list[str]
    risk_event_refs: list[str]
    error_event_refs: list[str]


FORBIDDEN_INLINE_STATE_KEYS = frozenset(
    {
        "pdf",
        "pdf_text",
        "raw_dataset",
        "processed_dataset",
        "frozen_dataset",
        "source_code",
        "student_code",
        "analysis_code",
        "image",
        "execution_log",
        "full_evidence",
        "full_conversation",
    }
)


def validate_reference_only_state(state: ResearchState) -> None:
    """Reject known large-object fields and obvious binary payloads before checkpointing."""

    forbidden = FORBIDDEN_INLINE_STATE_KEYS & set(state)
    if forbidden:
        raise ValueError(f"Large objects are forbidden in ResearchState: {sorted(forbidden)}")
    for key, value in state.items():
        if isinstance(value, (bytes, bytearray, memoryview)):
            raise TypeError(f"Binary value is forbidden in ResearchState: {key}")

"""Deterministic reducers for append-only workflow references."""

from __future__ import annotations

from collections.abc import Iterable

from .enums import TaskStatus
from .state import ResearchState


def _unique(existing: Iterable[str], incoming: Iterable[str]) -> list[str]:
    values: list[str] = []
    for value in [*existing, *incoming]:
        if value not in values:
            values.append(value)
    return values


def merge_references(
    state: ResearchState,
    *,
    task_status: dict[str, TaskStatus] | None = None,
    task_ledger: Iterable[str] = (),
    progress_ledger: Iterable[str] = (),
    evidence_refs: Iterable[str] = (),
    context_bundle_refs: Iterable[str] = (),
    rework_trigger_refs: Iterable[str] = (),
    artifact_refs: Iterable[str] = (),
    data_asset_refs: Iterable[str] = (),
    execution_run_refs: Iterable[str] = (),
    protocol_refs: Iterable[str] = (),
    research_test_result_refs: Iterable[str] = (),
    risk_profile_refs: Iterable[str] = (),
    route_decision_refs: Iterable[str] = (),
    agent_run_refs: Iterable[str] = (),
    approval_request_refs: Iterable[str] = (),
    long_memory_refs: Iterable[str] = (),
    risk_flags: Iterable[str] = (),
    unresolved_questions: Iterable[str] = (),
    error_log: Iterable[str] = (),
) -> ResearchState:
    """Merge references without changing stage or overwriting existing ledgers."""

    updates: dict[str, object] = {}
    for field, incoming in {
        "task_ledger": task_ledger,
        "progress_ledger": progress_ledger,
        "evidence_refs": evidence_refs,
        "context_bundle_refs": context_bundle_refs,
        "rework_trigger_refs": rework_trigger_refs,
        "artifact_refs": artifact_refs,
        "data_asset_refs": data_asset_refs,
        "execution_run_refs": execution_run_refs,
        "protocol_refs": protocol_refs,
        "research_test_result_refs": research_test_result_refs,
        "risk_profile_refs": risk_profile_refs,
        "route_decision_refs": route_decision_refs,
        "agent_run_refs": agent_run_refs,
        "approval_request_refs": approval_request_refs,
        "long_memory_refs": long_memory_refs,
        "risk_flags": risk_flags,
        "unresolved_questions": unresolved_questions,
        "error_log": error_log,
    }.items():
        updates[field] = _unique(getattr(state, field), incoming)
    if task_status:
        updates["task_status"] = {**state.task_status, **task_status}
    return state.model_copy(update=updates)

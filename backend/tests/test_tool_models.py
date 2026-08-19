from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from stem_sci.tools.models import (
    ToolExecutionMode,
    ToolResult,
    ToolRunRecord,
    ToolRunStatus,
    ToolSpec,
)


def _spec(**overrides: object) -> ToolSpec:
    values: dict[str, object] = {
        "tool_id": "context_bundle_read",
        "tool_version": "v1",
        "capability": "context_bundle_read",
        "execution_mode": ToolExecutionMode.READ_ONLY,
        "input_schema_ref": "schema://ContextRef",
        "output_schema_ref": "schema://ContextBundle",
        "project_scope_required": True,
        "network_policy": "disabled",
        "timeout_seconds": 10,
    }
    values.update(overrides)
    return ToolSpec(**values)


def test_tool_spec_rejects_unknown_execution_mode() -> None:
    with pytest.raises(ValidationError):
        _spec(execution_mode="INVALID")


def test_tool_spec_defaults_are_safe_and_strict() -> None:
    spec = _spec()

    assert spec.execution_mode is ToolExecutionMode.READ_ONLY
    assert spec.project_scope_required is True
    assert spec.network_policy == "disabled"
    assert spec.required_permissions == []
    assert spec.idempotency_policy == "required"
    with pytest.raises(ValidationError):
        _spec(unexpected="value")


def test_tool_result_and_run_record_share_status_contract() -> None:
    result = ToolResult(
        tool_run_id="tool-run-1",
        project_id="project-1",
        tool_id="context_bundle_read",
        tool_version="v1",
        status=ToolRunStatus.BLOCKED,
        error_code="policy.network_disabled",
    )
    record = ToolRunRecord(
        **result.model_dump(),
        agent_id="evidence_review",
        agent_run_id="agent-run-1",
        skill_ref="skill://bounded-corpus-review/v1",
        request_ref="tool-request://1",
        started_at=datetime.now(UTC),
    )

    assert record.status is ToolRunStatus.BLOCKED
    assert record.error_code == "policy.network_disabled"


def test_tool_spec_rejects_invalid_timeout_and_network_policy() -> None:
    with pytest.raises(ValidationError):
        _spec(timeout_seconds=0)
    with pytest.raises(ValidationError):
        _spec(network_policy="enabled")

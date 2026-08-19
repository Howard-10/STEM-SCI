"""Small, testable policy primitives used by the Tool Gateway."""

from __future__ import annotations

from collections.abc import Sequence

from stem_sci.artifacts.decision_store import DecisionStore
from stem_sci.tools.models import ToolExecutionMode, ToolSpec


class ToolPolicyError(ValueError):
    """A policy denial that should be represented as a BLOCKED ToolResult."""

    def __init__(self, error_code: str, message: str | None = None) -> None:
        self.error_code = error_code
        super().__init__(message or error_code)


def validate_project_scope(project_id: str, refs: Sequence[str]) -> None:
    """Reject URI references whose first path component names another project."""
    for reference in refs:
        if "://" not in reference:
            continue
        scheme, _, remainder = reference.partition("://")
        if scheme not in {"artifact", "artifact-content", "source", "context", "evidence"}:
            continue
        owner = remainder.split("/", 1)[0]
        # context://initial is a global bootstrap reference, not a project ref.
        if owner and owner not in {project_id, "initial"}:
            raise ToolPolicyError(
                "PROJECT_SCOPE_VIOLATION",
                f"reference {reference!r} belongs to another project",
            )


def validate_spec_policy(spec: ToolSpec) -> None:
    if spec.network_policy != "disabled":
        raise ToolPolicyError(
            "NETWORK_POLICY_UNSUPPORTED",
            f"network policy {spec.network_policy!r} is not enabled",
        )


def validate_approval(
    spec: ToolSpec,
    project_id: str,
    approval_refs: Sequence[str],
    decision_store: DecisionStore,
) -> None:
    if spec.execution_mode is not ToolExecutionMode.CONTROLLED_WRITE:
        return
    if not approval_refs or not any(
        (decision := decision_store.get(project_id, ref)) is not None
        and decision.decision == "approved"
        for ref in approval_refs
    ):
        raise ToolPolicyError("APPROVAL_REQUIRED", "controlled writes require an approved decision")


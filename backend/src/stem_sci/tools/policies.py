"""Small, testable policy primitives used by the Tool Gateway."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

from stem_sci.agents.contracts import ToolRequest
from stem_sci.artifacts.decision_store import DecisionStore
from stem_sci.tools.models import ToolExecutionMode, ToolSpec

ALLOWED_REFERENCE_SCHEMES = frozenset(
    {"artifact", "artifact-content", "source", "context", "evidence"}
)


class ToolPolicyError(ValueError):
    """A policy denial that should be represented as a BLOCKED ToolResult."""

    def __init__(self, error_code: str, message: str | None = None) -> None:
        self.error_code = error_code
        super().__init__(message or error_code)


@dataclass(frozen=True)
class ParsedToolReference:
    raw: str
    scheme: str
    project_id: str
    path_parts: tuple[str, ...]


def parse_tool_reference(
    reference: str, *, allow_initial_context: bool = False
) -> ParsedToolReference:
    """Parse only project-owned URI references accepted at the Tool boundary."""
    if allow_initial_context and reference == "context://initial":
        return ParsedToolReference(reference, "context", "initial", ())
    parsed = urlsplit(reference)
    if (
        parsed.scheme not in ALLOWED_REFERENCE_SCHEMES
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ToolPolicyError("REFERENCE_INVALID", f"invalid Tool reference {reference!r}")
    if parsed.netloc == "initial":
        raise ToolPolicyError("REFERENCE_INVALID", "initial context must use context://initial")
    path_parts = tuple(part for part in parsed.path.split("/") if part)
    if not path_parts:
        raise ToolPolicyError("REFERENCE_INVALID", f"reference has no target: {reference!r}")
    return ParsedToolReference(reference, parsed.scheme, parsed.netloc, path_parts)


def validate_project_scope(
    project_id: str,
    refs: Sequence[str],
    *,
    allow_initial_context: bool = True,
    require_project_owner: bool = True,
) -> None:
    """Reject malformed references and references owned by another project."""
    for reference in refs:
        parsed = parse_tool_reference(
            reference, allow_initial_context=allow_initial_context
        )
        if parsed.project_id == "initial":
            continue
        if require_project_owner and parsed.project_id != project_id:
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


def validate_permissions(spec: ToolSpec, granted_permissions: Sequence[str]) -> None:
    missing = sorted(set(spec.required_permissions).difference(granted_permissions))
    if missing:
        raise ToolPolicyError(
            "PERMISSION_REQUIRED", f"missing Tool permissions: {', '.join(missing)}"
        )


def tool_operation_key(project_id: str, spec: ToolSpec, request: ToolRequest) -> str:
    """Return the exact authorization fingerprint for one controlled operation."""
    body = {
        "project_id": project_id,
        "tool_id": spec.tool_id,
        "tool_version": spec.tool_version,
        "execution_mode": spec.execution_mode.value,
        "required_permissions": sorted(spec.required_permissions),
        "request": request.model_dump(mode="json", exclude={"reason"}),
    }
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"tool-operation:{hashlib.sha256(canonical.encode()).hexdigest()}"


def validate_approval(
    spec: ToolSpec,
    project_id: str,
    request: ToolRequest,
    approval_refs: Sequence[str],
    decision_store: DecisionStore,
) -> None:
    if spec.execution_mode is not ToolExecutionMode.CONTROLLED_WRITE:
        return
    if not approval_refs:
        raise ToolPolicyError("APPROVAL_REQUIRED", "controlled writes require approval")
    if request.target_artifact_ref is None or request.expected_output_hash is None:
        raise ToolPolicyError(
            "APPROVAL_CONTEXT_REQUIRED",
            "controlled writes require an exact target and expected hash",
        )
    target = parse_tool_reference(request.target_artifact_ref)
    if target.project_id != project_id:
        raise ToolPolicyError(
            "PROJECT_SCOPE_VIOLATION", "controlled-write target belongs to another project"
        )
    if target.scheme not in {"artifact", "artifact-content"} or len(target.path_parts) != 2:
        raise ToolPolicyError(
            "REFERENCE_INVALID", "controlled-write target must identify an artifact version"
        )
    artifact_id, raw_version = target.path_parts
    try:
        artifact_version = int(raw_version)
    except ValueError as error:
        raise ToolPolicyError(
            "REFERENCE_INVALID", "controlled-write target version must be an integer"
        ) from error
    operation_key = tool_operation_key(project_id, spec, request)
    for approval_ref in approval_refs:
        decision = decision_store.get(project_id, approval_ref)
        if (
            decision is not None
            and decision.decision == "approved"
            and decision.artifact_id == artifact_id
            and decision.artifact_version == artifact_version
            and decision.idempotency_key == operation_key
        ):
            return
    raise ToolPolicyError(
        "APPROVAL_SCOPE_MISMATCH",
        "approval is not bound to this Tool request, target version, and hash",
    )


__all__ = [
    "ParsedToolReference",
    "ToolPolicyError",
    "parse_tool_reference",
    "tool_operation_key",
    "validate_approval",
    "validate_permissions",
    "validate_project_scope",
    "validate_spec_policy",
]

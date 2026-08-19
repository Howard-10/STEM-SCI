"""Shared result and project-scope helpers for local Tools."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from stem_sci.tools.models import ToolRunStatus
from stem_sci.tools.policies import ToolPolicyError, parse_tool_reference

T = TypeVar("T")


@dataclass(frozen=True)
class BuiltinResult(Generic[T]):
    """A Tool payload with the same typed failure semantics as the Gateway."""

    status: ToolRunStatus = ToolRunStatus.SUCCEEDED
    value: T | None = None
    error_code: str | None = None
    risk_flags: list[str] = field(default_factory=list)

    def __getattr__(self, name: str) -> Any:
        if self.value is not None:
            return getattr(self.value, name)
        raise AttributeError(name)


def blocked(error_code: str, *, risk_flags: list[str] | None = None) -> BuiltinResult[None]:
    return BuiltinResult(
        status=ToolRunStatus.BLOCKED,
        error_code=error_code,
        risk_flags=risk_flags or [error_code],
    )


def failed(error_code: str) -> BuiltinResult[None]:
    return BuiltinResult(status=ToolRunStatus.FAILED, error_code=error_code)


def ensure_project(project_id: str, *refs: str) -> None:
    for reference in refs:
        parsed = parse_tool_reference(reference)
        if parsed.project_id != project_id:
            raise ToolPolicyError("PROJECT_SCOPE_VIOLATION", "reference belongs to another project")


def project_ref(project_id: str, reference: str) -> tuple[str, ...]:
    parsed = parse_tool_reference(reference)
    if parsed.project_id != project_id:
        raise ToolPolicyError("PROJECT_SCOPE_VIOLATION", "reference belongs to another project")
    return parsed.path_parts


R = TypeVar("R")


def run_or_block(function: Callable[..., R], *args: object, **kwargs: object) -> R | BuiltinResult[None]:
    try:
        return function(*args, **kwargs)
    except ToolPolicyError as error:
        return blocked(error.error_code)
    except (KeyError, LookupError):
        return failed("REFERENCE_NOT_FOUND")
    except (TypeError, ValueError):
        return failed("INVALID_INPUT")


def execute_wrapped(
    function: Callable[..., R], *args: object, **kwargs: object
) -> BuiltinResult[Any]:
    result: R | BuiltinResult[None] = run_or_block(function, *args, **kwargs)
    if isinstance(result, BuiltinResult):
        return result
    return BuiltinResult(value=result)

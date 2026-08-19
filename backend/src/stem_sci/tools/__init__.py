"""Typed contracts for Controller-governed tool execution.

The Gateway imports Controller budget and policy modules.  Keep it lazy here
so importing the lightweight contracts cannot create a Controller/Gateway
cycle during application startup.
"""

from .models import ToolExecutionMode, ToolResult, ToolRunRecord, ToolRunStatus, ToolSpec
from .registry import ToolRegistry


def __getattr__(name: str) -> object:
    if name in {"ToolExecutor", "ToolGateway", "ToolPolicyError"}:
        from .gateway import ToolExecutor, ToolGateway, ToolPolicyError

        return {"ToolExecutor": ToolExecutor, "ToolGateway": ToolGateway, "ToolPolicyError": ToolPolicyError}[name]
    raise AttributeError(name)

__all__ = [
    "ToolExecutionMode",
    "ToolExecutor",
    "ToolGateway",
    "ToolPolicyError",
    "ToolRegistry",
    "ToolResult",
    "ToolRunRecord",
    "ToolRunStatus",
    "ToolSpec",
]

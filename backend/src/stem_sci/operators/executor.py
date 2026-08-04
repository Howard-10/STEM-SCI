"""Controller-owned operator dispatch with explicit unsupported states."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from stem_sci.agents.contracts import ToolRequest
from stem_sci.artifacts.execution_store import ExecutionStore, InMemoryExecutionStore
from stem_sci.core.enums import RunStatus

from .models import OperatorRun
from .registry import OperatorRegistry


class OperatorExecutor:
    """Record operator requests without claiming unsupported execution succeeded."""

    def __init__(
        self,
        registry: OperatorRegistry | None = None,
        execution_store: ExecutionStore | None = None,
    ) -> None:
        self.registry = registry or OperatorRegistry.default()
        self.execution_store = execution_store or InMemoryExecutionStore()

    def execute_tool_requests(
        self,
        project_id: str,
        agent_run_id: str,
        tool_requests: Sequence[ToolRequest | str],
    ) -> list[OperatorRun]:
        runs: list[OperatorRun] = []
        for index, raw_request in enumerate(tool_requests):
            request = (
                raw_request
                if isinstance(raw_request, ToolRequest)
                else ToolRequest(
                    request_id=f"{agent_run_id}:legacy-tool:{index}",
                    capability=raw_request.removeprefix("request://"),
                    reason=f"Legacy Agent {agent_run_id} requested an operator.",
                )
            )
            runs.append(self.execute(project_id, request))
        return runs

    def execute(self, project_id: str, request: ToolRequest) -> OperatorRun:
        operator_id = request.capability.removesuffix("_request")
        operator_run_id = f"operator-{uuid4().hex}"
        now = datetime.now(UTC)
        try:
            spec = self.registry.get(operator_id)
        except ValueError:
            run = OperatorRun(
                operator_run_id=operator_run_id,
                project_id=project_id,
                operator_id=operator_id,
                operator_version="unresolved",
                request_ref=request.request_id,
                input_artifact_refs=request.input_refs,
                log_ref=f"log://{operator_run_id}",
                error_ref=f"error://operator/{operator_id}/unknown",
                status=RunStatus.FAILED,
                started_at=now,
                finished_at=now,
            )
        else:
            run = OperatorRun(
                operator_run_id=operator_run_id,
                project_id=project_id,
                operator_id=spec.operator_id,
                operator_version=spec.operator_version,
                request_ref=request.request_id,
                input_artifact_refs=request.input_refs,
                log_ref=f"log://{operator_run_id}",
                error_ref=f"error://operator/{spec.operator_id}/unsupported",
                status=RunStatus.BLOCKED,
                started_at=now,
                finished_at=now,
            )
        return self.execution_store.put(run)

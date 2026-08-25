"""Controller-owned operator dispatch with explicit unsupported states."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from stem_sci.agents.contracts import ToolRequest
from stem_sci.artifacts.execution_store import ExecutionStore, InMemoryExecutionStore
from stem_sci.context.models import ContextBundle
from stem_sci.core.enums import RunStatus
from stem_sci.statistics.python_operator import PythonAnalysisRequest, PythonExecutionOutcome

from .models import OperatorRun
from .knowledge import (
    OperatorExecutionContext,
    OperatorHandler,
)
from .registry import OperatorRegistry


class OperatorExecutor:
    """Dispatch registered operators and preserve explicit unsupported states."""

    def __init__(
        self,
        registry: OperatorRegistry | None = None,
        execution_store: ExecutionStore | None = None,
        handlers: Mapping[str, OperatorHandler] | None = None,
    ) -> None:
        self.registry = registry or OperatorRegistry.default()
        self.execution_store = execution_store or InMemoryExecutionStore()
        self.handlers = dict(handlers or {})

    def execute_tool_requests(
        self,
        project_id: str,
        agent_run_id: str,
        tool_requests: Sequence[ToolRequest | str],
        *,
        query: str = "",
        context_bundle: ContextBundle | None = None,
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
            runs.append(
                self.execute(
                    project_id,
                    request,
                    query=query,
                    context_bundle=context_bundle,
                    agent_run_id=agent_run_id,
                )
            )
        return runs

    def execute(
        self,
        project_id: str,
        request: ToolRequest,
        *,
        query: str = "",
        context_bundle: ContextBundle | None = None,
        agent_run_id: str | None = None,
    ) -> OperatorRun:
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
            if operator_id in self.handlers:
                execution_context = OperatorExecutionContext(
                    project_id=project_id,
                    agent_run_id=agent_run_id or request.request_id,
                    query=query,
                    context_bundle=context_bundle,
                )
                try:
                    outcome = self.handlers[operator_id](
                        project_id,
                        request,
                        execution_context,
                        operator_run_id,
                    )
                except (OSError, RuntimeError, ValueError) as error:
                    run = OperatorRun(
                        operator_run_id=operator_run_id,
                        project_id=project_id,
                        operator_id=operator_id,
                        operator_version=spec.operator_version,
                        request_ref=request.request_id,
                        input_artifact_refs=request.input_refs,
                        log_ref=f"log://{operator_run_id}",
                        error_ref=f"error://operator/{operator_id}/{type(error).__name__}",
                        status=RunStatus.FAILED,
                        started_at=now,
                        finished_at=datetime.now(UTC),
                    )
                else:
                    run = OperatorRun(
                        operator_run_id=operator_run_id,
                        project_id=project_id,
                        operator_id=operator_id,
                        operator_version=spec.operator_version,
                        request_ref=request.request_id,
                        input_artifact_refs=request.input_refs,
                        output_artifact_refs=outcome.output_artifact_refs,
                        log_ref=f"log://{operator_run_id}",
                        error_ref=outcome.error_ref,
                        status=outcome.status,
                        started_at=now,
                        finished_at=datetime.now(UTC),
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

    def execute_python_only(
        self, request: PythonAnalysisRequest, output_root: Path
    ) -> PythonExecutionOutcome:
        """Controller entry point for the real CSV/PYTHON_ONLY MVP operator.

        This deliberately bypasses Agent ToolRequest generation: the Controller
        calls it only after the relevant plan and data approvals have completed.
        """

        from stem_sci.statistics.python_operator import CsvPythonAnalysisOperator

        return CsvPythonAnalysisOperator(execution_store=self.execution_store).execute(
            request, output_root
        )

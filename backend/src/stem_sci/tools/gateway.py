"""Controller-owned Tool execution boundary."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from stem_sci.agents.contracts import ToolRequest
from stem_sci.artifacts.artifact_store import ArtifactStore
from stem_sci.artifacts.content_store import ArtifactContent, ArtifactContentStore
from stem_sci.artifacts.decision_store import DecisionStore
from stem_sci.artifacts.models import ArtifactRef
from stem_sci.controller.budget.budget_manager import BudgetManager
from stem_sci.skills.registry import SkillRegistry
from stem_sci.tools.models import (
    ToolExecutionMode,
    ToolResult,
    ToolRunRecord,
    ToolRunStatus,
    ToolSpec,
)
from stem_sci.tools.policies import (
    ToolPolicyError,
    validate_approval,
    validate_project_scope,
    validate_spec_policy,
)
from stem_sci.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from stem_sci.provenance.tool_run_store import ToolRunStore


class ToolExecutor(Protocol):
    def execute(
        self,
        spec: ToolSpec,
        project_id: str,
        agent_id: str,
        agent_run_id: str,
        request: ToolRequest,
    ) -> ToolResult: ...


class UnavailableToolExecutor:
    """Default executor; unsupported Tools fail explicitly rather than succeeding."""

    def execute(
        self,
        spec: ToolSpec,
        project_id: str,
        agent_id: str,
        agent_run_id: str,
        request: ToolRequest,
    ) -> ToolResult:
        return ToolResult(
            tool_run_id="pending",
            project_id=project_id,
            tool_id=spec.tool_id,
            tool_version=spec.tool_version,
            status=ToolRunStatus.BLOCKED,
            error_code="TOOL_EXECUTOR_UNAVAILABLE",
        )


class ToolGateway:
    """Resolve, authorize, execute, and audit one structured Tool request."""

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry,
        skill_registry: SkillRegistry | None = None,
        tool_run_store: ToolRunStore | None = None,
        artifact_store: ArtifactStore | None = None,
        artifact_content_store: ArtifactContentStore | None = None,
        decision_store: DecisionStore | None = None,
        budget_manager: BudgetManager | None = None,
        executor: ToolExecutor | None = None,
        model_backed_tool_ids: Sequence[str] = (),
    ) -> None:
        self.tool_registry = tool_registry
        self.skill_registry = skill_registry or SkillRegistry()
        if tool_run_store is None:
            from stem_sci.provenance.tool_run_store import InMemoryToolRunStore

            tool_run_store = InMemoryToolRunStore()
        self.tool_run_store = tool_run_store
        self.artifact_store = artifact_store
        self.artifact_content_store = artifact_content_store
        self.decision_store = decision_store
        self.budget_manager = budget_manager or BudgetManager()
        self.executor = executor or UnavailableToolExecutor()
        self.model_backed_tool_ids = frozenset(model_backed_tool_ids)

    def execute(
        self,
        *,
        project_id: str,
        agent_id: str,
        agent_run_id: str,
        request: ToolRequest,
        approval_refs: Sequence[str] = (),
    ) -> ToolResult:
        tool_run_id = f"tool-{uuid4().hex}"
        started_at = datetime.now(UTC)
        spec: ToolSpec | None = None
        skill_ref = "skill://unresolved"
        try:
            spec = self._resolve_spec(request.capability)
            skill_ref = self._resolve_skill_ref(agent_id, spec)
            validate_project_scope(project_id, request.input_refs)
            validate_spec_policy(spec)
            if spec.required_permissions:
                raise ToolPolicyError("PERMISSION_REQUIRED", "Tool permissions are not granted")
            if self.decision_store is None:
                if spec.execution_mode is ToolExecutionMode.CONTROLLED_WRITE:
                    raise ToolPolicyError("APPROVAL_REQUIRED", "no decision store is configured")
            else:
                validate_approval(spec, project_id, approval_refs, self.decision_store)
            if self._is_model_backed(spec) and not self.budget_manager.can_use_llm():
                raise ToolPolicyError("LLM_BUDGET_EXCEEDED", "model-backed Tool budget exceeded")
            if self._is_model_backed(spec):
                self.budget_manager.consume_llm()
            raw_result = self.executor.execute(
                spec, project_id, agent_id, agent_run_id, request
            )
            result = raw_result.model_copy(
                update={
                    "tool_run_id": tool_run_id,
                    "project_id": project_id,
                    "tool_id": spec.tool_id,
                    "tool_version": spec.tool_version,
                }
            )
            if result.status is ToolRunStatus.SUCCEEDED:
                self._persist_payloads(result, project_id, tool_run_id, started_at)
        except ToolPolicyError as error:
            result = self._result(
                tool_run_id,
                project_id,
                spec,
                ToolRunStatus.BLOCKED,
                error.error_code,
            )
        except (KeyError, TypeError, ValueError, RuntimeError):
            result = self._result(
                tool_run_id,
                project_id,
                spec,
                ToolRunStatus.FAILED,
                "TOOL_EXECUTION_FAILED",
            )
        record = ToolRunRecord(
            **result.model_dump(),
            agent_id=agent_id,
            agent_run_id=agent_run_id,
            skill_ref=skill_ref,
            request_ref=request.request_id,
            input_artifact_refs=list(request.input_refs),
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )
        self.tool_run_store.put(record)
        return result

    def _resolve_spec(self, capability: str) -> ToolSpec:
        tool_id, separator, version = capability.partition("@")
        try:
            matches = self.tool_registry.resolve(tool_id) if not separator else [
                self.tool_registry.get(tool_id, version)
            ]
        except (KeyError, ValueError) as error:
            raise ToolPolicyError("TOOL_NOT_AUTHORIZED", f"unknown Tool {capability}") from error
        if not matches:
            raise ToolPolicyError("TOOL_NOT_AUTHORIZED", f"unknown Tool {capability}")
        if len(matches) > 1:
            raise ToolPolicyError("TOOL_VERSION_REQUIRED", f"Tool version is required for {tool_id}")
        return matches[0]

    def _resolve_skill_ref(self, agent_id: str, spec: ToolSpec) -> str:
        required_ref = f"{spec.tool_id}@{spec.tool_version}"
        matches = [
            manifest
            for manifest in self.skill_registry.list()
            if agent_id in manifest.agent_ids
            and required_ref in manifest.required_tool_ids
        ]
        if not matches:
            # A registry-less Gateway remains useful for migration and tests;
            # once manifests are configured, an Agent must be explicitly bound.
            if self.skill_registry.list():
                raise ToolPolicyError(
                    "SKILL_NOT_AUTHORIZED",
                    f"Agent {agent_id} is not bound to Tool {required_ref}",
                )
            return "skill://legacy"
        return f"{matches[0].skill_id}@{matches[0].skill_version}"

    def _is_model_backed(self, spec: ToolSpec) -> bool:
        return spec.tool_id in self.model_backed_tool_ids or bool(
            getattr(self.executor, "model_backed", False)
        )

    def _persist_payloads(
        self, result: ToolResult, project_id: str, tool_run_id: str, created_at: datetime
    ) -> None:
        if not result.output_payloads or self.artifact_content_store is None:
            return
        content_refs: list[str] = list(result.output_content_refs)
        for index, payload in enumerate(result.output_payloads):
            body = payload.get("body")
            if not isinstance(body, dict):
                raise TypeError("Tool output payload body must be an object")
            artifact_id = str(payload.get("artifact_id", f"{tool_run_id}:output:{index}"))
            artifact_type = str(payload.get("artifact_type", "ToolOutput"))
            schema_version = str(payload.get("schema_version", "v1"))
            content = self.artifact_content_store.put(
                ArtifactContent(
                    project_id=project_id,
                    artifact_id=artifact_id,
                    version=1,
                    artifact_type=artifact_type,
                    schema_version=schema_version,
                    body=body,
                    created_at=created_at,
                )
            )
            content_refs.append(
                f"artifact-content://{project_id}/{content.artifact_id}/{content.version}"
            )
            if self.artifact_store is not None:
                artifact_ref = ArtifactRef(
                    artifact_id=content.artifact_id,
                    project_id=project_id,
                    artifact_type=content.artifact_type,
                    version=content.version,
                    content_uri=content_refs[-1],
                    sha256=content.content_hash or "",
                    created_at=created_at,
                    created_by="tool-gateway",
                )
                self.artifact_store.put(artifact_ref)
        # ToolResult is immutable by contract; the references are carried in the
        # persisted audit record even when the executor returned only payloads.
        result.output_content_refs[:] = content_refs

    @staticmethod
    def _result(
        tool_run_id: str,
        project_id: str,
        spec: ToolSpec | None,
        status: ToolRunStatus,
        error_code: str,
    ) -> ToolResult:
        return ToolResult(
            tool_run_id=tool_run_id,
            project_id=project_id,
            tool_id=spec.tool_id if spec is not None else "unresolved",
            tool_version=spec.tool_version if spec is not None else "unresolved",
            status=status,
            error_code=error_code,
        )


__all__ = ["ToolExecutor", "ToolGateway", "ToolPolicyError"]

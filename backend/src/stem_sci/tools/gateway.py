"""Controller-owned Tool execution boundary."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from pydantic import JsonValue, ValidationError

from stem_sci.agents.contracts import ToolRequest
from stem_sci.artifacts.artifact_store import ArtifactStore
from stem_sci.artifacts.content_store import ArtifactContent, ArtifactContentStore
from stem_sci.artifacts.decision_store import DecisionStore
from stem_sci.artifacts.models import ArtifactRef
from stem_sci.controller.budget.budget_manager import BudgetManager
from stem_sci.skills.registry import SkillRegistry
from stem_sci.tools.models import (
    CandidateOutputPayload,
    ToolExecutionMode,
    ToolResult,
    ToolRunRecord,
    ToolRunStatus,
    ToolSpec,
)
from stem_sci.tools.policies import (
    ToolPolicyError,
    tool_operation_key,
    validate_approval,
    validate_permissions,
    validate_project_scope,
    validate_spec_policy,
)
from stem_sci.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from stem_sci.provenance.tool_run_store import ToolRunStore


SAFE_ERROR_CODES = frozenset(
    {
        "APPROVAL_CONTEXT_REQUIRED",
        "APPROVAL_REQUIRED",
        "APPROVAL_SCOPE_MISMATCH",
        "CANDIDATE_CONFLICT",
        "EXECUTION_CANCELLED",
        "EXECUTION_FAILED",
        "EXECUTION_MODE_VIOLATION",
        "HASH_MISMATCH",
        "IDEMPOTENCY_CONFLICT",
        "LLM_BUDGET_EXCEEDED",
        "NETWORK_POLICY_UNSUPPORTED",
        "PERMISSION_REQUIRED",
        "PERSISTENCE_UNAVAILABLE",
        "PROJECT_SCOPE_VIOLATION",
        "REFERENCE_INVALID",
        "SCHEMA_INVALID",
        "SKILL_NOT_AUTHORIZED",
        "TIMEOUT",
        "TOOL_EXECUTION_BLOCKED",
        "TOOL_EXECUTOR_UNAVAILABLE",
        "TOOL_NOT_AUTHORIZED",
        "TOOL_VERSION_REQUIRED",
    }
)


class ToolOutputError(ValueError):
    """An expected executor-output failure represented by a typed result."""

    def __init__(self, error_code: str, message: str | None = None) -> None:
        self.error_code = error_code
        super().__init__(message or error_code)


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
        granted_permissions: Sequence[str] = (),
    ) -> ToolResult:
        tool_run_id = f"tool-{uuid4().hex}"
        started_at = datetime.now(UTC)
        spec: ToolSpec | None = None
        skill_ref = "skill://unresolved"
        idempotency_key: str | None = None
        operation_hash: str | None = None
        try:
            # References are parsed before registry resolution so malformed or
            # cross-project data never reaches a resolver or legacy fallback.
            validate_project_scope(project_id, request.input_refs)
            if request.target_artifact_ref is not None:
                validate_project_scope(
                    project_id,
                    [request.target_artifact_ref],
                    allow_initial_context=False,
                )
            spec = self._resolve_spec(request.capability)
            skill_ref = self._resolve_skill_ref(agent_id, spec)
            validate_spec_policy(spec)
            validate_permissions(spec, granted_permissions)
            idempotency_key = self._idempotency_key(spec, request)
            operation_hash = tool_operation_key(project_id, spec, request)
            existing = self._idempotent_result(
                project_id,
                request,
                spec,
                idempotency_key,
                operation_hash,
            )
            if existing is not None:
                return existing
            if spec.execution_mode is ToolExecutionMode.CONTROLLED_WRITE:
                if self.decision_store is None:
                    raise ToolPolicyError(
                        "APPROVAL_REQUIRED", "no decision store is configured"
                    )
                validate_approval(
                    spec,
                    project_id,
                    request,
                    approval_refs,
                    self.decision_store,
                )
            if self._is_model_backed(spec) and not self.budget_manager.can_use_llm():
                raise ToolPolicyError(
                    "LLM_BUDGET_EXCEEDED", "model-backed Tool budget exceeded"
                )
            if self._is_model_backed(spec):
                self.budget_manager.consume_llm()
            raw_result = self.executor.execute(
                spec, project_id, agent_id, agent_run_id, request
            )
            result = self._normalize_result(
                raw_result, spec, project_id, tool_run_id, started_at, request
            )
        except ToolPolicyError as error:
            result = self._result(
                tool_run_id,
                project_id,
                spec,
                ToolRunStatus.BLOCKED,
                error.error_code,
            )
            if error.error_code == "IDEMPOTENCY_CONFLICT":
                idempotency_key = None
        except ToolOutputError as error:
            result = self._result(
                tool_run_id,
                project_id,
                spec,
                ToolRunStatus.FAILED,
                error.error_code,
            )
        except TimeoutError:
            result = self._result(
                tool_run_id,
                project_id,
                spec,
                ToolRunStatus.TIMED_OUT,
                "TIMEOUT",
            )
        except ValidationError:
            result = self._result(
                tool_run_id,
                project_id,
                spec,
                ToolRunStatus.FAILED,
                "SCHEMA_INVALID",
            )
        except OSError:
            result = self._result(
                tool_run_id,
                project_id,
                spec,
                ToolRunStatus.FAILED,
                "EXECUTION_FAILED",
            )
        except (RuntimeError, ValueError):
            result = self._result(
                tool_run_id,
                project_id,
                spec,
                ToolRunStatus.FAILED,
                "EXECUTION_FAILED",
            )
        record = ToolRunRecord(
            tool_run_id=result.tool_run_id,
            project_id=result.project_id,
            tool_id=result.tool_id,
            tool_version=result.tool_version,
            status=result.status,
            output_artifact_refs=list(result.output_artifact_refs),
            output_content_refs=list(result.output_content_refs),
            risk_flags=self._audit_risk_codes(result.risk_flags),
            error_code=self._safe_error_code(result.status, result.error_code),
            agent_id=agent_id,
            agent_run_id=agent_run_id,
            skill_ref=skill_ref,
            request_ref=request.request_id,
            idempotency_key=idempotency_key,
            operation_hash=operation_hash,
            input_artifact_refs=list(request.input_refs),
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )
        self.tool_run_store.put(record)
        return result.model_copy(
            update={
                "output_payloads": [],
                "risk_flags": list(record.risk_flags),
                "error_code": record.error_code,
            }
        )

    def _resolve_spec(self, capability: str) -> ToolSpec:
        tool_id, separator, version = capability.partition("@")
        try:
            matches = (
                self.tool_registry.resolve(tool_id)
                if not separator
                else [self.tool_registry.get(tool_id, version)]
            )
        except (KeyError, ValueError) as error:
            raise ToolPolicyError(
                "TOOL_NOT_AUTHORIZED", f"unknown Tool {capability}"
            ) from error
        if not matches:
            raise ToolPolicyError("TOOL_NOT_AUTHORIZED", f"unknown Tool {capability}")
        if len(matches) > 1:
            raise ToolPolicyError(
                "TOOL_VERSION_REQUIRED", f"Tool version is required for {tool_id}"
            )
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

    @staticmethod
    def _idempotency_key(spec: ToolSpec, request: ToolRequest) -> str | None:
        if spec.idempotency_policy == "none":
            return None
        if request.idempotency_key is not None:
            return request.idempotency_key
        if spec.idempotency_policy == "required":
            return request.request_id
        return None

    def _idempotent_result(
        self,
        project_id: str,
        request: ToolRequest,
        spec: ToolSpec,
        idempotency_key: str | None,
        operation_hash: str,
    ) -> ToolResult | None:
        existing = (
            self.tool_run_store.get_by_request(project_id, request.request_id)
            if idempotency_key is not None
            else None
        )
        if existing is None and idempotency_key is not None:
            existing = self.tool_run_store.get_by_idempotency(
                project_id, idempotency_key
            )
        if existing is None:
            return None
        if (
            spec.idempotency_policy != "none"
            and existing.operation_hash == operation_hash
        ):
            return self._record_result(existing)
        raise ToolPolicyError(
            "IDEMPOTENCY_CONFLICT",
            "request or idempotency key is already bound to another operation",
        )

    def _normalize_result(
        self,
        raw: ToolResult,
        spec: ToolSpec,
        project_id: str,
        tool_run_id: str,
        created_at: datetime,
        request: ToolRequest,
    ) -> ToolResult:
        if raw.project_id != project_id:
            raise ToolOutputError(
                "PROJECT_SCOPE_VIOLATION", "executor returned another project"
            )
        if raw.tool_id != spec.tool_id or raw.tool_version != spec.tool_version:
            raise ToolOutputError("SCHEMA_INVALID", "executor returned wrong Tool identity")
        try:
            validate_project_scope(
                project_id,
                [*raw.output_artifact_refs, *raw.output_content_refs],
                allow_initial_context=False,
            )
        except ToolPolicyError as error:
            raise ToolOutputError(error.error_code, str(error)) from error
        terminal = {
            ToolRunStatus.SUCCEEDED,
            ToolRunStatus.BLOCKED,
            ToolRunStatus.FAILED,
            ToolRunStatus.TIMED_OUT,
            ToolRunStatus.CANCELLED,
        }
        if raw.status not in terminal:
            raise ToolOutputError("SCHEMA_INVALID", "executor returned non-terminal status")
        if raw.status is not ToolRunStatus.SUCCEEDED:
            return ToolResult(
                tool_run_id=tool_run_id,
                project_id=project_id,
                tool_id=spec.tool_id,
                tool_version=spec.tool_version,
                status=raw.status,
                output_artifact_refs=list(raw.output_artifact_refs),
                output_content_refs=list(raw.output_content_refs),
                risk_flags=self._audit_risk_codes(raw.risk_flags),
                error_code=self._safe_error_code(raw.status, raw.error_code),
                output_data=raw.output_data,
            )
        if raw.error_code is not None:
            raise ToolOutputError("SCHEMA_INVALID", "successful result included an error")
        content_refs = list(raw.output_content_refs)
        if raw.output_payloads:
            if spec.execution_mode is not ToolExecutionMode.CANDIDATE_OUTPUT:
                raise ToolOutputError(
                    "EXECUTION_MODE_VIOLATION",
                    "only CANDIDATE_OUTPUT Tools may return persistable payloads",
                )
            content_refs.extend(
                self._persist_candidates(
                    raw.output_payloads,
                    spec,
                    project_id,
                    created_at,
                    expected_hash=request.expected_output_hash,
                )
            )
        return ToolResult(
            tool_run_id=tool_run_id,
            project_id=project_id,
            tool_id=spec.tool_id,
            tool_version=spec.tool_version,
            status=ToolRunStatus.SUCCEEDED,
            output_artifact_refs=list(raw.output_artifact_refs),
            output_content_refs=content_refs,
            risk_flags=self._audit_risk_codes(raw.risk_flags),
            output_data=raw.output_data,
        )

    def _persist_candidates(
        self,
        raw_payloads: list[dict[str, JsonValue]],
        spec: ToolSpec,
        project_id: str,
        created_at: datetime,
        expected_hash: str | None = None,
    ) -> list[str]:
        if self.artifact_content_store is None:
            raise ToolOutputError(
                "PERSISTENCE_UNAVAILABLE", "candidate content store is not configured"
            )
        candidates: list[CandidateOutputPayload] = []
        seen: set[tuple[str, int]] = set()
        for raw_payload in raw_payloads:
            try:
                candidate = CandidateOutputPayload.model_validate(raw_payload)
            except ValidationError as error:
                raise ToolOutputError("SCHEMA_INVALID", "invalid candidate payload") from error
            if candidate.project_id != project_id:
                raise ToolOutputError(
                    "PROJECT_SCOPE_VIOLATION", "candidate belongs to another project"
                )
            if candidate.schema_ref != spec.output_schema_ref:
                raise ToolOutputError(
                    "SCHEMA_INVALID", "candidate output schema does not match Tool spec"
                )
            if candidate.content_hash != self._body_hash(candidate.body):
                raise ToolOutputError("HASH_MISMATCH", "candidate content hash mismatch")
            if expected_hash is not None and candidate.content_hash != expected_hash:
                raise ToolOutputError("HASH_MISMATCH", "candidate hash differs from request")
            key = (candidate.artifact_id, candidate.version)
            if key in seen:
                raise ToolOutputError(
                    "CANDIDATE_CONFLICT", "candidate batch contains duplicate version"
                )
            seen.add(key)
            if (
                self.artifact_content_store.get(
                    project_id, candidate.artifact_id, candidate.version
                )
                is not None
                or (
                    self.artifact_store is not None
                    and self.artifact_store.get(
                        project_id, candidate.artifact_id, candidate.version
                    )
                    is not None
                )
            ):
                raise ToolOutputError(
                    "CANDIDATE_CONFLICT", "candidate version already exists"
                )
            candidates.append(candidate)

        contents = [
            ArtifactContent(
                project_id=project_id,
                artifact_id=candidate.artifact_id,
                version=candidate.version,
                artifact_type=candidate.artifact_type,
                schema_version=candidate.schema_version,
                body=candidate.body,
                content_hash=candidate.content_hash,
                created_at=created_at,
            )
            for candidate in candidates
        ]
        refs = [
            ArtifactRef(
                artifact_id=content.artifact_id,
                project_id=project_id,
                artifact_type=content.artifact_type,
                version=content.version,
                content_uri=(
                    f"artifact-content://{project_id}/{content.artifact_id}/{content.version}"
                ),
                sha256=content.content_hash or "",
                created_at=created_at,
                created_by="tool-gateway",
            )
            for content in contents
        ]
        inserted_contents: list[ArtifactContent] = []
        inserted_refs: list[ArtifactRef] = []
        try:
            for content in contents:
                self.artifact_content_store.put(content)
                inserted_contents.append(content)
            if self.artifact_store is not None:
                for artifact_ref in refs:
                    self.artifact_store.put(artifact_ref)
                    inserted_refs.append(artifact_ref)
        except Exception:
            if self.artifact_store is not None:
                for artifact_ref in reversed(inserted_refs):
                    self.artifact_store.delete(
                        project_id, artifact_ref.artifact_id, artifact_ref.version
                    )
            for content in reversed(inserted_contents):
                self.artifact_content_store.delete(
                    project_id, content.artifact_id, content.version
                )
            raise
        return [artifact_ref.content_uri for artifact_ref in refs]

    @staticmethod
    def _body_hash(body: Mapping[str, object]) -> str:
        canonical = json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _audit_risk_codes(risk_flags: Sequence[str]) -> list[str]:
        return list(dict.fromkeys(code for code in risk_flags if code in SAFE_ERROR_CODES))

    @staticmethod
    def _safe_error_code(
        status: ToolRunStatus, error_code: str | None
    ) -> str | None:
        if status is ToolRunStatus.SUCCEEDED:
            return None
        if status is ToolRunStatus.TIMED_OUT:
            return "TIMEOUT"
        if status is ToolRunStatus.CANCELLED:
            return "EXECUTION_CANCELLED"
        if error_code in SAFE_ERROR_CODES:
            return error_code
        if status is ToolRunStatus.BLOCKED:
            return "TOOL_EXECUTION_BLOCKED"
        return "EXECUTION_FAILED"

    @staticmethod
    def _record_result(record: ToolRunRecord) -> ToolResult:
        return ToolResult(
            tool_run_id=record.tool_run_id,
            project_id=record.project_id,
            tool_id=record.tool_id,
            tool_version=record.tool_version,
            status=record.status,
            output_artifact_refs=list(record.output_artifact_refs),
            output_content_refs=list(record.output_content_refs),
            risk_flags=list(record.risk_flags),
            error_code=record.error_code,
        )

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

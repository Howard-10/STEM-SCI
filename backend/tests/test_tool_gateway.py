import hashlib
import json
from datetime import UTC, datetime

import pytest

from stem_sci.agents.contracts import AgentResult, ToolRequest
from stem_sci.artifacts.artifact_store import InMemoryArtifactStore
from stem_sci.artifacts.content_store import InMemoryArtifactContentStore
from stem_sci.artifacts.decision_store import InMemoryDecisionStore
from stem_sci.controller import ResearchController
from stem_sci.controller.budget.budget_manager import BudgetManager, BudgetState
from stem_sci.core.models import ApprovalRecord
from stem_sci.core.state import ResearchState
from stem_sci.provenance.tool_run_store import InMemoryToolRunStore
from stem_sci.tools.gateway import ToolGateway
from stem_sci.tools.models import ToolExecutionMode, ToolResult, ToolRunStatus, ToolSpec
from stem_sci.tools.policies import tool_operation_key
from stem_sci.tools.registry import ToolRegistry


def _spec(
    tool_id: str,
    mode: ToolExecutionMode = ToolExecutionMode.READ_ONLY,
    *,
    required_permissions: list[str] | None = None,
    idempotency_policy: str = "required",
) -> ToolSpec:
    return ToolSpec(
        tool_id=tool_id,
        tool_version="v1",
        capability=tool_id,
        execution_mode=mode,
        input_schema_ref="schema://Input",
        output_schema_ref="schema://Output",
        required_permissions=required_permissions or [],
        timeout_seconds=10,
        idempotency_policy=idempotency_policy,  # type: ignore[arg-type]
    )


def _content_hash(body: dict[str, object]) -> str:
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _candidate_payload(
    *,
    project_id: str = "project-a",
    artifact_id: str = "candidate-1",
    version: int = 1,
    body: dict[str, object] | None = None,
) -> dict[str, object]:
    candidate_body = body or {"ok": True}
    return {
        "project_id": project_id,
        "artifact_id": artifact_id,
        "version": version,
        "artifact_type": "ToolCandidate",
        "schema_ref": "schema://Output",
        "schema_version": "v1",
        "body": candidate_body,
        "content_hash": _content_hash(candidate_body),
    }


class FakeExecutor:
    def __init__(
        self,
        *,
        payloads: list[dict[str, object]] | None = None,
        output_content_refs: list[str] | None = None,
        status: ToolRunStatus = ToolRunStatus.SUCCEEDED,
        error_code: str | None = None,
    ) -> None:
        self.payloads = payloads or []
        self.output_content_refs = output_content_refs or []
        self.status = status
        self.error_code = error_code
        self.calls = 0

    def execute(self, spec, project_id, agent_id, agent_run_id, request):
        self.calls += 1
        return ToolResult(
            tool_run_id="executor-run",
            project_id=project_id,
            tool_id=spec.tool_id,
            tool_version=spec.tool_version,
            status=self.status,
            output_content_refs=self.output_content_refs,
            error_code=self.error_code,
            output_payloads=self.payloads,
        )


class RaisingExecutor:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def execute(self, spec, project_id, agent_id, agent_run_id, request):
        raise self.error


def _request(
    capability: str,
    *,
    request_id: str = "request-1",
    input_refs: list[str] | None = None,
    idempotency_key: str | None = None,
    target_artifact_ref: str | None = None,
    expected_output_hash: str | None = None,
) -> ToolRequest:
    return ToolRequest(
        request_id=request_id,
        capability=capability,
        input_refs=input_refs or [],
        idempotency_key=idempotency_key,
        target_artifact_ref=target_artifact_ref,
        expected_output_hash=expected_output_hash,
        reason="test request",
    )


def _gateway(
    spec: ToolSpec,
    *,
    executor=None,
    decision_store=None,
    tool_run_store=None,
    artifact_store=None,
    content_store=None,
) -> ToolGateway:
    return ToolGateway(
        tool_registry=ToolRegistry([spec]),
        executor=executor or FakeExecutor(),
        decision_store=decision_store,
        tool_run_store=tool_run_store,
        artifact_store=artifact_store,
        artifact_content_store=content_store,
    )


def _execute(gateway: ToolGateway, request: ToolRequest, **kwargs) -> ToolResult:
    return gateway.execute(
        project_id="project-a",
        agent_id="evidence_review",
        agent_run_id="run-1",
        request=request,
        **kwargs,
    )


def test_gateway_validates_input_refs_before_tool_resolution() -> None:
    gateway = ToolGateway(tool_registry=ToolRegistry(), executor=FakeExecutor())
    result = _execute(
        gateway,
        _request("unknown", input_refs=["artifact://project-b/source-1"]),
    )
    assert result.status is ToolRunStatus.BLOCKED
    assert result.error_code == "PROJECT_SCOPE_VIOLATION"


@pytest.mark.parametrize(
    "reference",
    ["raw-secret", "unknown://project-a/x", "artifact:///empty", "context://initial/extra"],
)
def test_gateway_rejects_malformed_or_unapproved_initial_refs(reference: str) -> None:
    result = _execute(
        _gateway(_spec("knowledge_base_search")),
        _request("knowledge_base_search", input_refs=[reference]),
    )
    assert result.status is ToolRunStatus.BLOCKED
    assert result.error_code == "REFERENCE_INVALID"


def test_gateway_allows_only_exact_initial_context_reference() -> None:
    result = _execute(
        _gateway(_spec("knowledge_base_search")),
        _request("knowledge_base_search", input_refs=["context://initial"]),
    )
    assert result.status is ToolRunStatus.SUCCEEDED


def test_gateway_rejects_cross_project_output_reference() -> None:
    executor = FakeExecutor(
        output_content_refs=["artifact-content://project-b/candidate-1/1"]
    )
    result = _execute(
        _gateway(_spec("candidate_writer", ToolExecutionMode.CANDIDATE_OUTPUT), executor=executor),
        _request("candidate_writer"),
    )
    assert result.status is ToolRunStatus.FAILED
    assert result.error_code == "PROJECT_SCOPE_VIOLATION"


def test_read_only_tool_cannot_persist_payloads() -> None:
    contents = InMemoryArtifactContentStore()
    result = _execute(
        _gateway(
            _spec("context_read"),
            executor=FakeExecutor(payloads=[_candidate_payload()]),
            content_store=contents,
        ),
        _request("context_read"),
    )
    assert result.status is ToolRunStatus.FAILED
    assert result.error_code == "EXECUTION_MODE_VIOLATION"
    assert contents.list_project("project-a") == []


def test_gateway_persists_validated_candidate_output() -> None:
    contents = InMemoryArtifactContentStore()
    artifacts = InMemoryArtifactStore()
    result = _execute(
        _gateway(
            _spec("candidate_writer", ToolExecutionMode.CANDIDATE_OUTPUT),
            executor=FakeExecutor(payloads=[_candidate_payload()]),
            artifact_store=artifacts,
            content_store=contents,
        ),
        _request("candidate_writer"),
    )
    assert result.status is ToolRunStatus.SUCCEEDED
    assert result.output_payloads == []
    assert result.output_content_refs == ["artifact-content://project-a/candidate-1/1"]
    assert contents.get("project-a", "candidate-1", 1) is not None
    assert artifacts.get("project-a", "candidate-1", 1) is not None


def test_candidate_batch_is_validated_before_any_write() -> None:
    contents = InMemoryArtifactContentStore()
    invalid = _candidate_payload(artifact_id="candidate-2")
    invalid["schema_ref"] = "schema://Wrong"
    result = _execute(
        _gateway(
            _spec("candidate_writer", ToolExecutionMode.CANDIDATE_OUTPUT),
            executor=FakeExecutor(payloads=[_candidate_payload(), invalid]),
            content_store=contents,
        ),
        _request("candidate_writer"),
    )
    assert result.status is ToolRunStatus.FAILED
    assert result.error_code == "SCHEMA_INVALID"
    assert contents.list_project("project-a") == []


class FailingArtifactStore(InMemoryArtifactStore):
    def put(self, artifact):
        raise OSError("artifact store unavailable")


def test_candidate_write_rolls_back_content_when_reference_write_fails() -> None:
    contents = InMemoryArtifactContentStore()
    result = _execute(
        _gateway(
            _spec("candidate_writer", ToolExecutionMode.CANDIDATE_OUTPUT),
            executor=FakeExecutor(payloads=[_candidate_payload()]),
            artifact_store=FailingArtifactStore(),
            content_store=contents,
        ),
        _request("candidate_writer"),
    )
    assert result.status is ToolRunStatus.FAILED
    assert result.error_code == "EXECUTION_FAILED"
    assert contents.list_project("project-a") == []


def test_candidate_hash_mismatch_has_stable_error_and_no_write() -> None:
    contents = InMemoryArtifactContentStore()
    invalid = _candidate_payload()
    invalid["content_hash"] = "f" * 64
    result = _execute(
        _gateway(
            _spec("candidate_writer", ToolExecutionMode.CANDIDATE_OUTPUT),
            executor=FakeExecutor(payloads=[invalid]),
            content_store=contents,
        ),
        _request("candidate_writer"),
    )
    assert result.status is ToolRunStatus.FAILED
    assert result.error_code == "HASH_MISMATCH"
    assert contents.list_project("project-a") == []


def test_candidate_versions_never_overwrite_existing_content() -> None:
    contents = InMemoryArtifactContentStore()
    gateway = _gateway(
        _spec("candidate_writer", ToolExecutionMode.CANDIDATE_OUTPUT),
        executor=FakeExecutor(payloads=[_candidate_payload()]),
        content_store=contents,
    )
    first = _execute(gateway, _request("candidate_writer", request_id="request-1"))
    second = _execute(gateway, _request("candidate_writer", request_id="request-2"))
    assert first.status is ToolRunStatus.SUCCEEDED
    assert second.status is ToolRunStatus.FAILED
    assert second.error_code == "CANDIDATE_CONFLICT"
    assert len(contents.list_versions("project-a", "candidate-1")) == 1


def test_audit_projection_never_contains_transient_payload_or_raw_error() -> None:
    sentinel = "sk-secret-raw-provider-response"
    store = InMemoryToolRunStore()
    executor = FakeExecutor(
        payloads=[_candidate_payload(body={"raw_response": sentinel})],
        status=ToolRunStatus.FAILED,
        error_code=sentinel,
    )
    result = _execute(
        _gateway(_spec("candidate_writer"), executor=executor, tool_run_store=store),
        _request("candidate_writer"),
    )
    record = store.get("project-a", result.tool_run_id)
    assert record is not None
    assert sentinel not in record.model_dump_json()
    assert "output_payloads" not in record.model_dump()
    assert record.error_code == "EXECUTION_FAILED"
    assert result.output_payloads == []


@pytest.mark.parametrize(
    ("error", "status", "error_code"),
    [
        (TimeoutError("slow"), ToolRunStatus.TIMED_OUT, "TIMEOUT"),
        (OSError("provider failed"), ToolRunStatus.FAILED, "EXECUTION_FAILED"),
    ],
)
def test_expected_executor_errors_have_stable_codes(
    error: Exception, status: ToolRunStatus, error_code: str
) -> None:
    result = _execute(
        _gateway(_spec("context_read"), executor=RaisingExecutor(error)),
        _request("context_read"),
    )
    assert result.status is status
    assert result.error_code == error_code


def test_required_permissions_can_be_explicitly_granted() -> None:
    gateway = _gateway(_spec("context_read", required_permissions=["controller_dispatch"]))
    blocked = _execute(gateway, _request("context_read", request_id="request-1"))
    allowed = _execute(
        gateway,
        _request("context_read", request_id="request-2"),
        granted_permissions=["controller_dispatch"],
    )
    assert blocked.error_code == "PERMISSION_REQUIRED"
    assert allowed.status is ToolRunStatus.SUCCEEDED


def test_controlled_write_requires_approval_bound_to_exact_operation() -> None:
    spec = _spec(
        "controlled_writer",
        ToolExecutionMode.CONTROLLED_WRITE,
        required_permissions=["controller_dispatch"],
    )
    request = _request(
        "controlled_writer",
        target_artifact_ref="artifact-content://project-a/candidate-1/2",
        expected_output_hash="a" * 64,
    )
    decisions = InMemoryDecisionStore()
    decisions.put(
        ApprovalRecord(
            approval_id="approval-wrong",
            project_id="project-a",
            artifact_id="candidate-1",
            artifact_version=2,
            decision="approved",
            decided_by="reviewer",
            decided_at=datetime.now(UTC),
            idempotency_key="different-operation",
        )
    )
    gateway = _gateway(spec, decision_store=decisions)
    blocked = _execute(
        gateway,
        request,
        approval_refs=["approval-wrong"],
        granted_permissions=["controller_dispatch"],
    )
    decisions.put(
        ApprovalRecord(
            approval_id="approval-exact",
            project_id="project-a",
            artifact_id="candidate-1",
            artifact_version=2,
            decision="approved",
            decided_by="reviewer",
            decided_at=datetime.now(UTC),
            idempotency_key=tool_operation_key("project-a", spec, request),
        )
    )
    allowed = _execute(
        gateway,
        request.model_copy(update={"request_id": "request-2"}),
        approval_refs=["approval-exact"],
        granted_permissions=["controller_dispatch"],
    )
    assert blocked.error_code == "APPROVAL_SCOPE_MISMATCH"
    assert allowed.status is ToolRunStatus.BLOCKED
    assert allowed.error_code == "APPROVAL_SCOPE_MISMATCH"


def test_controlled_write_accepts_approval_for_the_same_exact_request() -> None:
    spec = _spec("controlled_writer", ToolExecutionMode.CONTROLLED_WRITE)
    request = _request(
        "controlled_writer",
        target_artifact_ref="artifact-content://project-a/candidate-1/2",
        expected_output_hash="a" * 64,
    )
    decisions = InMemoryDecisionStore()
    decisions.put(
        ApprovalRecord(
            approval_id="approval-exact",
            project_id="project-a",
            artifact_id="candidate-1",
            artifact_version=2,
            decision="approved",
            decided_by="reviewer",
            decided_at=datetime.now(UTC),
            idempotency_key=tool_operation_key("project-a", spec, request),
        )
    )
    result = _execute(
        _gateway(spec, decision_store=decisions),
        request,
        approval_refs=["approval-exact"],
    )
    assert result.status is ToolRunStatus.SUCCEEDED


def test_required_idempotent_request_returns_existing_run_without_reexecution() -> None:
    executor = FakeExecutor()
    store = InMemoryToolRunStore()
    gateway = _gateway(
        _spec("context_read"), executor=executor, tool_run_store=store
    )
    request = _request("context_read", idempotency_key="read-context-1")
    first = _execute(gateway, request)
    second = _execute(gateway, request)
    assert second == first
    assert executor.calls == 1
    assert len(store.list_project("project-a")) == 1


def test_reused_idempotency_key_cannot_authorize_changed_request() -> None:
    gateway = _gateway(_spec("context_read"))
    first = _execute(
        gateway,
        _request(
            "context_read",
            input_refs=["artifact://project-a/source-1"],
            idempotency_key="read-context-1",
        ),
    )
    conflict = _execute(
        gateway,
        _request(
            "context_read",
            request_id="request-2",
            input_refs=["artifact://project-a/source-2"],
            idempotency_key="read-context-1",
        ),
    )
    assert first.status is ToolRunStatus.SUCCEEDED
    assert conflict.status is ToolRunStatus.BLOCKED
    assert conflict.error_code == "IDEMPOTENCY_CONFLICT"


class RecordingGateway:
    def __init__(self) -> None:
        self.approval_refs: tuple[str, ...] = ()
        self.granted_permissions: tuple[str, ...] = ()
        self.allowed_skill_refs: tuple[str, ...] = ()

    def execute(self, **kwargs) -> ToolResult:
        self.approval_refs = tuple(kwargs["approval_refs"])
        self.granted_permissions = tuple(kwargs["granted_permissions"])
        self.allowed_skill_refs = tuple(kwargs["allowed_skill_refs"])
        request = kwargs["request"]
        return ToolResult(
            tool_run_id="tool-success",
            project_id=kwargs["project_id"],
            tool_id=request.capability,
            tool_version="v1",
            status=ToolRunStatus.SUCCEEDED,
        )


def test_controller_passes_approved_refs_and_explicit_permissions_to_gateway() -> None:
    decisions = InMemoryDecisionStore()
    decisions.put(
        ApprovalRecord(
            approval_id="approval-1",
            project_id="project-a",
            artifact_id="candidate-1",
            artifact_version=1,
            decision="approved",
            decided_by="reviewer",
            decided_at=datetime.now(UTC),
            idempotency_key="approval-1",
        )
    )
    gateway = RecordingGateway()
    controller = ResearchController(
        decision_store=decisions,
        tool_gateway=gateway,  # type: ignore[arg-type]
        tool_permissions=["controller_dispatch"],
    )
    controller._states["project-a"] = ResearchState(
        project_id="project-a", approval_request_refs=["approval-1"]
    )
    result = AgentResult(
        agent_run_id="run-1",
        agent_id="evidence_review",
        agent_version="v1",
        tool_requests=[_request("context_read")],
        created_at=datetime.now(UTC),
    )
    refs, risks = controller._execute_agent_tools(
        "project-a", result, allowed_skill_refs=["bounded_corpus_review@v1"]
    )
    assert refs == ["tool-success"]
    assert risks == []
    assert gateway.approval_refs == ("approval-1",)
    assert gateway.granted_permissions == ("controller_dispatch",)
    assert gateway.allowed_skill_refs == ("bounded_corpus_review@v1",)


class BlockedGateway(RecordingGateway):
    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            tool_run_id="tool-blocked",
            project_id=kwargs["project_id"],
            tool_id=kwargs["request"].capability,
            tool_version="v1",
            status=ToolRunStatus.BLOCKED,
            error_code="PERMISSION_REQUIRED",
        )


def test_controller_excludes_failed_or_blocked_tool_runs_from_execution_refs() -> None:
    controller = ResearchController(tool_gateway=BlockedGateway())  # type: ignore[arg-type]
    result = AgentResult(
        agent_run_id="run-1",
        agent_id="evidence_review",
        agent_version="v1",
        tool_requests=[_request("context_read@v1")],
        created_at=datetime.now(UTC),
    )
    refs, risks = controller._execute_agent_tools("project-a", result)
    assert refs == []
    assert risks == ["PERMISSION_REQUIRED"]


def test_gateway_consumes_budget_only_for_model_backed_tools() -> None:
    budget = BudgetManager(BudgetState(max_llm_calls=1))
    gateway = ToolGateway(
        tool_registry=ToolRegistry([_spec("model_tool")]),
        executor=FakeExecutor(),
        budget_manager=budget,
        model_backed_tool_ids=["model_tool"],
    )
    assert _execute(gateway, _request("model_tool")).status is ToolRunStatus.SUCCEEDED
    assert budget.state.used_llm_calls == 1

from datetime import UTC, datetime

import pytest

from stem_sci.artifacts.artifact_store import InMemoryArtifactStore
from stem_sci.artifacts.decision_store import InMemoryDecisionStore
from stem_sci.artifacts.models import ArtifactRef
from stem_sci.context.models import (
    ContextBundle,
    EvidenceRef,
    SourceLocation,
    VerificationStatus,
)
from stem_sci.controller import PlanningRequest, ResearchController
from stem_sci.core.enums import ProjectStage, TaskStatus
from stem_sci.core.models import ApprovalRecord
from stem_sci.core.reducers import merge_references
from stem_sci.core.state import ResearchState
from stem_sci.operators.models import OperatorSpec
from stem_sci.operators.registry import OperatorRegistry


def test_research_state_is_reference_only_and_project_scoped() -> None:
    state = ResearchState(project_id="physics-demo")

    merged = merge_references(
        state,
        artifact_refs=["artifact://protocol/1", "artifact://protocol/1"],
        evidence_refs=["evidence://paper-1"],
        risk_flags=["CITATION_RISK"],
    )

    assert merged.project_id == "physics-demo"
    assert merged.current_stage is ProjectStage.INTAKE
    assert merged.artifact_refs == ["artifact://protocol/1"]
    assert merged.evidence_refs == ["evidence://paper-1"]
    assert merged.risk_flags == ["CITATION_RISK"]
    with pytest.raises(ValueError):
        ResearchState(project_id="physics-demo", full_pdf="not allowed")  # type: ignore[call-arg]


def test_reducer_preserves_append_only_ledgers_and_status() -> None:
    state = ResearchState(
        project_id="demo",
        task_status={"planning": TaskStatus.DONE},
        progress_ledger=["planning-complete"],
    )

    merged = merge_references(
        state,
        progress_ledger=["planning-complete", "evidence-needed"],
        task_status={"evidence": TaskStatus.READY},
    )

    assert merged.progress_ledger == ["planning-complete", "evidence-needed"]
    assert merged.task_status == {"planning": TaskStatus.DONE, "evidence": TaskStatus.READY}
    assert state.progress_ledger == ["planning-complete"]


def test_versioned_artifact_and_decision_stores_are_project_scoped() -> None:
    store = InMemoryArtifactStore()
    artifact = ArtifactRef(
        artifact_id="protocol-1",
        artifact_type="ResearchContractCandidate",
        version=1,
        content_uri="candidate://mentor/protocol-1",
        sha256="a" * 64,
        created_at=datetime.now(UTC),
        created_by="mentor_planning",
        project_id="physics-demo",
    )
    store.put(artifact)

    assert store.get("physics-demo", "protocol-1") == artifact
    assert store.list_versions("physics-demo", "protocol-1") == [artifact]
    assert store.get("other-project", "protocol-1") is None

    decision_store = InMemoryDecisionStore()
    approval = ApprovalRecord(
        approval_id="approval-1",
        project_id="physics-demo",
        artifact_id="protocol-1",
        artifact_version=1,
        decision="approved",
        decided_by="researcher",
        decided_at=datetime.now(UTC),
        reason="scope accepted",
        idempotency_key="approve:protocol-1:v1",
    )
    decision_store.put(approval)
    assert decision_store.get("physics-demo", "approval-1") == approval
    assert decision_store.get("other-project", "approval-1") is None


def test_controller_routes_from_scope_to_evidence_and_pauses_again() -> None:
    controller = ResearchController()
    first = controller.start_planning(
        PlanningRequest(
            project_id="physics-demo",
            research_intent="研究分层 AI 支架对 Python 物理建模迁移能力的影响",
            run_id="planning-1",
        )
    )
    scoped = controller.approve_planning(first.workflow_state, first.approval_request)

    next_run = controller.run_next("physics-demo")

    assert scoped.current_stage is ProjectStage.SCOPED
    assert next_run.route_decision.selected_route == "evidence_review"
    assert next_run.workflow_state.current_stage is ProjectStage.WAITING_HUMAN
    assert next_run.approval_request.approval_type == "evidence_protocol"


def test_controller_approval_resume_is_idempotent() -> None:
    controller = ResearchController()
    first = controller.start_planning(
        PlanningRequest(project_id="demo", research_intent="scope", run_id="planning-2")
    )

    resumed = controller.resume_approval(
        "demo",
        first.approval_request,
        decision="approved",
        decided_by="researcher",
    )
    repeated = controller.resume_approval(
        "demo",
        first.approval_request,
        decision="approved",
        decided_by="researcher",
    )

    assert resumed.current_stage is ProjectStage.SCOPED
    assert repeated == resumed


def test_operator_registry_exposes_explicit_capabilities() -> None:
    registry = OperatorRegistry.default()
    specs = registry.resolve("literature_search")

    assert specs
    assert all(isinstance(spec, OperatorSpec) for spec in specs)
    assert registry.get("python_analysis").capability == "python_analysis"


def test_evidence_agent_preserves_context_evidence_refs() -> None:
    from stem_sci.agents import AgentInput, EvidenceReviewAgent

    bundle = ContextBundle(
        context_id="ctx-1",
        project_id="physics-demo",
        task_ref="evidence",
        query="Python 物理建模",
        evidence_refs=[
            EvidenceRef(
                evidence_id="evidence-1",
                project_id="physics-demo",
                source_id="paper-1",
                chunk_id="chunk-1",
                excerpt="计算建模可通过新任务评价迁移能力。",
                location=SourceLocation(chunk_index=0, char_start=0, char_end=18),
                verification_status=VerificationStatus.SOURCE_VERIFIED,
            )
        ],
        source_refs=["paper-1"],
        unresolved_questions=["需要确认迁移测量指标"],
        verification_summary={"source_verified": 1},
        token_budget=500,
        estimated_tokens=20,
        context_hash="b" * 64,
        generated_at="2026-08-04T00:00:00Z",
    )
    agent = EvidenceReviewAgent()
    result = agent.run_with_context(
        AgentInput(
            agent_run_id="evidence-run-1",
            task_ref="physics-demo:evidence",
            context_bundle_ref="ctx-1",
            allowed_tool_capabilities=list(agent.allowed_tool_capabilities),
            allowed_output_types=list(agent.allowed_output_types),
            policy_version="policy-v1",
            prompt_template_version="evidence-v1",
        ),
        bundle,
    )

    assert result.evidence_refs == ["evidence-1"]
    assert "candidate://evidence_review/physics-demo:evidence/EvidenceMatrixCandidate" in result.candidate_artifact_refs
    assert "INSUFFICIENT_VERIFIED_EVIDENCE" not in result.risk_flags
    assert "需要确认迁移测量指标" in result.unresolved_questions


def test_controller_builds_context_before_evidence_review() -> None:
    from stem_sci.context.models import ContextBundle

    class Provider:
        def build_context(self, project_id: str, task_ref: str, query: str, token_budget: int) -> ContextBundle:
            return ContextBundle(
                context_id="ctx-controller",
                project_id=project_id,
                task_ref=task_ref,
                query=query,
                evidence_refs=[],
                source_refs=[],
                unresolved_questions=["需要补充物理建模迁移证据"],
                risk_flags=["insufficient_verified_evidence"],
                verification_summary={},
                token_budget=token_budget,
                estimated_tokens=0,
                context_hash="c" * 64,
                generated_at="2026-08-04T00:00:00Z",
            )

    controller = ResearchController(context_provider=Provider())
    first = controller.start_planning(
        PlanningRequest(project_id="context-demo", research_intent="研究 Python 物理建模迁移", run_id="p-ctx")
    )
    controller.approve_planning(first.workflow_state, first.approval_request)
    run = controller.run_next("context-demo")

    assert run.agent_result.evidence_refs == []
    state = run.workflow_state.research_state
    assert state is not None
    assert state.context_bundle_refs == ["ctx-controller"]
    assert "insufficient_verified_evidence" in state.risk_flags

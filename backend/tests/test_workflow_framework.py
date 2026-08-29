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
from stem_sci.agents import AgentInput, MentorPlanningAgent
from stem_sci.core.enums import ProjectStage, TaskStatus
from stem_sci.core.models import ApprovalRecord
from stem_sci.core.reducers import merge_references
from stem_sci.core.state import ResearchState
from stem_sci.operators.models import OperatorSpec
from stem_sci.operators.registry import OperatorRegistry
from stem_sci.agents.runtime import FakeLLMProvider, StructuredGenerator


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


def test_controller_builds_real_research_design_candidates_after_evidence_approval() -> None:
    from stem_sci.context.models import ContextBundle, EvidenceRef, SourceLocation, VerificationStatus

    class VerifiedProvider:
        def build_context(self, project_id: str, task_ref: str, query: str, token_budget: int) -> ContextBundle:
            evidence = EvidenceRef(
                evidence_id=f"{project_id}-evidence-1",
                project_id=project_id,
                source_id="source-1",
                chunk_id="chunk-1",
                excerpt="Verified evidence for computational physics education.",
                location=SourceLocation(chunk_index=0, char_start=0, char_end=55, page_start=1, page_end=1),
                verification_status=VerificationStatus.SOURCE_VERIFIED,
            )
            return ContextBundle(
                context_id=f"context-{task_ref}", project_id=project_id, task_ref=task_ref, query=query,
                evidence_refs=[evidence], source_refs=["source-1"], verification_summary={
                    VerificationStatus.SOURCE_VERIFIED.value: 1
                }, token_budget=token_budget, estimated_tokens=20, context_hash="d" * 64,
                generated_at="2026-08-21T00:00:00Z",
            )

    controller = ResearchController(context_provider=VerifiedProvider())
    project_id = "design-route-demo"
    planning = controller.start_planning(PlanningRequest(
        project_id=project_id,
        research_intent=(
            "设计师范生 Python 物理建模实验；研究对象：大一物理师范生；"
            "研究场景：大学物理实验室；干预与对照：分层AI支架 vs 常规提示；"
            "主要指标：迁移得分"
        ),
    ))
    controller.resume_approval(project_id, planning.approval_request, decision="approved", decided_by="researcher")
    evidence = controller.run_next(project_id)
    controller.resume_approval(project_id, evidence.approval_request, decision="approved", decided_by="researcher")

    design = controller.run_next(project_id)

    assert design.route_decision.selected_route == "research_design"
    assert any(ref.endswith("/StudyProtocolCandidate") for ref in design.agent_result.candidate_artifact_refs)
    contents = controller.workflow_timeline(project_id).artifact_contents
    assert any(item.artifact_type == "StudyProtocolCandidate" for item in contents)


def test_planning_brief_extracts_clarifications_from_human_feedback() -> None:
    agent_input = AgentInput(
        agent_run_id="planning-clarified",
        task_ref="demo:planning",
        context_bundle_ref="context://initial",
        allowed_output_types=list(MentorPlanningAgent.allowed_output_types),
        allowed_tool_capabilities=[],
        policy_version="policy-v1",
        prompt_template_version="planner-v1",
    )
    brief = ResearchController._build_planning_brief(
        "demo",
        agent_input,
        "AI物理建模；研究对象：华东师范大学物理师范生；研究场景：大学物理实验课程；"
        "干预与对照：分层AI支架 vs 常规提示；主要指标：建模迁移得分。",
    )
    assert brief.population == "华东师范大学物理师范生"
    assert brief.context == "大学物理实验课程"
    assert brief.intervention == "分层AI支架"
    assert brief.comparator == "常规提示"
    assert brief.candidate_outcomes == ["建模迁移得分"]


def test_base_agent_attaches_llm_reasoning_candidate_when_configured() -> None:
    from stem_sci.agents import ResearchDesignAgent

    agent = ResearchDesignAgent(
        reasoning_generator=StructuredGenerator(FakeLLMProvider([{
            "summary": "根据已批准范围评估研究设计风险。",
            "key_decisions": ["保留预注册边界"],
            "open_questions": ["确认测量工具"],
            "risk_flags": ["需要人工审批"],
        }])),
        reasoning_model="fake-model",
    )
    result = agent.run(AgentInput(
        agent_run_id="design-llm",
        task_ref="demo:design",
        context_bundle_ref="context://demo",
        allowed_tool_capabilities=[],
        allowed_output_types=["AgentReasoningCandidate"],
        policy_version="policy-v1",
        prompt_template_version="design-v1",
    ))
    assert result.candidate_artifacts[0].artifact_type == "AgentReasoningCandidate"
    assert result.llm_metadata_refs[0].startswith("llm-metadata://")


def test_planner_pipeline_extracts_natural_language_brief() -> None:
    from stem_sci.agents import MentorPlanningPipeline

    pipeline = MentorPlanningPipeline(
        generator=StructuredGenerator(FakeLLMProvider([{
            "population": "物理师范生",
            "context": "力学实验课",
            "intervention": "分层 AI 支架",
            "comparator": "常规提示",
            "primary_outcome": "建模迁移得分",
            "clarifying_questions": ["确认样本量"],
        }])),
        model="fake-model",
    )
    brief = ResearchController._build_planning_brief(
        "demo",
        AgentInput(
            agent_run_id="planner-extract",
            task_ref="demo:planning",
            context_bundle_ref="context://demo",
            allowed_output_types=[],
            allowed_tool_capabilities=[],
            policy_version="policy-v1",
            prompt_template_version="planner-v1",
        ),
        "我想研究 AI 对物理建模的影响",
    )
    enriched = ResearchController._llm_enrich_planning_brief(
        MentorPlanningAgent(pipeline=pipeline), brief, "我想研究 AI 对物理建模的影响"
    )
    assert enriched.population == "物理师范生"
    assert enriched.candidate_outcomes == ["建模迁移得分"]


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

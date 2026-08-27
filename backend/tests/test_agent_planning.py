from datetime import UTC, datetime

import pytest

from stem_sci.artifacts.artifact_store import InMemoryArtifactStore
from stem_sci.artifacts.content_store import ArtifactContent, InMemoryArtifactContentStore
from stem_sci.artifacts.models import ArtifactRef
from stem_sci.controller import (
    AgentExecutionMode,
    AgentExecutionPlan,
    AgentOutputDecisionRequest,
    AgentPlanApprovalRequest,
    AgentPlanRequest,
    AgentPlanStatus,
    AgentTaskApprovalRequest,
    AgentTaskPlan,
    AgentTaskStatus,
    ResearchController,
)
from stem_sci.agents.evidence import EvidenceReviewAgent
from stem_sci.agents.contracts import AgentInput
from stem_sci.context.models import ContextBundle, EvidenceRef, SourceLocation, VerificationStatus


def test_natural_language_agent_plan_requires_approval_before_execution() -> None:
    controller = ResearchController()

    plan = controller.plan_agent_tasks(
        AgentPlanRequest(
            project_id="agent-plan-demo",
            user_request="根据当前证据设计前测、后测和迁移任务，并检查方法风险。",
            conversation_id="conversation-1",
            turn_id="turn-1",
            context_refs=["context://conversation-1/turn-1"],
        )
    )

    assert plan.status is AgentPlanStatus.PENDING_APPROVAL
    assert {task.agent_id for task in plan.tasks} >= {"evidence_review", "research_design", "independent_review"}
    assert plan.conversation_id == "conversation-1"
    assert plan.turn_id == "turn-1"

    with pytest.raises(ValueError, match="approved before execution"):
        controller.execute_agent_plan("agent-plan-demo", plan.plan_id)


def test_agent_plan_approval_records_selected_tasks_only() -> None:
    controller = ResearchController()
    plan = controller.plan_agent_tasks(
        AgentPlanRequest(
            project_id="agent-selection-demo",
            user_request="请做证据审查和研究设计。",
        )
    )
    selected = [plan.tasks[0].task_id]

    approved = controller.approve_agent_plan(
        "agent-selection-demo",
        plan.plan_id,
        AgentPlanApprovalRequest(
            decision="approved",
            decided_by="researcher",
            selected_task_ids=selected,
        ),
    )

    assert approved.status is AgentPlanStatus.APPROVED
    assert approved.approved_task_ids == selected
    assert [
        task.status for task in approved.tasks if task.task_id not in selected
    ] == [AgentTaskStatus.SKIPPED]


def test_stepwise_plan_runs_one_task_then_requires_human_confirmation() -> None:
    controller = ResearchController()
    plan = AgentExecutionPlan(
        plan_id="stepwise-demo",
        project_id="stepwise-demo",
        user_request="先制定研究计划，再审查证据。",
        intent_summary="按依赖顺序完成研究计划与证据审查。",
        tasks=[
            AgentTaskPlan(
                task_id="task-planning",
                agent_id="mentor_planning",
                task_type="plan_research",
                reason="先确定研究计划。",
                expected_output_types=["ResearchQuestionTree"],
            ),
            AgentTaskPlan(
                task_id="task-evidence",
                agent_id="evidence_review",
                task_type="synthesize_evidence",
                reason="依据计划审查证据。",
                depends_on=["agent:mentor_planning"],
                expected_output_types=["EvidenceMatrixCandidate"],
            ),
        ],
    )
    controller.agent_plan_store.put(plan)
    executed_task_ids: list[str] = []

    def complete_task(
        project_id: str,
        execution_plan: AgentExecutionPlan,
        task: AgentTaskPlan,
    ) -> AgentTaskPlan:
        assert project_id == "stepwise-demo"
        assert execution_plan.plan_id == "stepwise-demo"
        executed_task_ids.append(task.task_id)
        return task.model_copy(
            update={
                "status": AgentTaskStatus.COMPLETED,
                "persisted_artifact_ids": [f"artifact-{task.task_id}"],
            }
        )

    controller._execute_planned_task = complete_task  # type: ignore[method-assign]
    approved = controller.approve_agent_plan(
        "stepwise-demo",
        plan.plan_id,
        AgentPlanApprovalRequest(
            decision="approved",
            decided_by="researcher",
            execution_mode=AgentExecutionMode.STEPWISE,
        ),
    )

    first_pause = controller.execute_agent_plan("stepwise-demo", approved.plan_id)
    assert executed_task_ids == ["task-planning"]
    assert first_pause.status is AgentPlanStatus.WAITING_TASK_APPROVAL
    assert first_pause.pending_review_task_id == "task-planning"
    assert first_pause.tasks[1].status is AgentTaskStatus.PLANNED

    second_pause = controller.continue_agent_plan(
        "stepwise-demo",
        approved.plan_id,
        AgentTaskApprovalRequest(decision="approved", decided_by="researcher", note="计划可以继续。"),
    )
    assert executed_task_ids == ["task-planning", "task-evidence"]
    assert second_pause.status is AgentPlanStatus.WAITING_TASK_APPROVAL
    assert second_pause.pending_review_task_id == "task-evidence"
    assert second_pause.tasks[0].review_note == "计划可以继续。"

    completed = controller.continue_agent_plan(
        "stepwise-demo",
        approved.plan_id,
        AgentTaskApprovalRequest(decision="approved", decided_by="researcher"),
    )
    assert completed.status is AgentPlanStatus.COMPLETED
    assert executed_task_ids == ["task-planning", "task-evidence"]


def test_stepwise_rework_stops_downstream_tasks() -> None:
    controller = ResearchController()
    plan = AgentExecutionPlan(
        plan_id="stepwise-rework-demo",
        project_id="stepwise-rework-demo",
        user_request="先制定研究计划，再审查证据。",
        intent_summary="按依赖顺序完成研究计划与证据审查。",
        tasks=[
            AgentTaskPlan(
                task_id="task-planning",
                agent_id="mentor_planning",
                task_type="plan_research",
                reason="先确定研究计划。",
                expected_output_types=["ResearchQuestionTree"],
            ),
            AgentTaskPlan(
                task_id="task-evidence",
                agent_id="evidence_review",
                task_type="synthesize_evidence",
                reason="依据计划审查证据。",
                depends_on=["agent:mentor_planning"],
                expected_output_types=["EvidenceMatrixCandidate"],
            ),
        ],
    )
    controller.agent_plan_store.put(plan)

    def complete_task(
        _project_id: str,
        _execution_plan: AgentExecutionPlan,
        task: AgentTaskPlan,
    ) -> AgentTaskPlan:
        return task.model_copy(update={"status": AgentTaskStatus.COMPLETED})

    controller._execute_planned_task = complete_task  # type: ignore[method-assign]
    controller.approve_agent_plan(
        "stepwise-rework-demo",
        plan.plan_id,
        AgentPlanApprovalRequest(
            decision="approved",
            decided_by="researcher",
            execution_mode=AgentExecutionMode.STEPWISE,
        ),
    )
    paused = controller.execute_agent_plan("stepwise-rework-demo", plan.plan_id)
    returned = controller.continue_agent_plan(
        "stepwise-rework-demo",
        plan.plan_id,
        AgentTaskApprovalRequest(
            decision="rework",
            decided_by="researcher",
            note="研究计划需要重写变量定义。",
        ),
    )

    assert paused.pending_review_task_id == "task-planning"
    assert returned.status is AgentPlanStatus.REWORK_REQUIRED
    assert returned.rework_note == "研究计划需要重写变量定义。"
    assert returned.tasks[1].status is AgentTaskStatus.PLANNED


def test_agent_output_box_lists_persisted_previews_and_decisions() -> None:
    controller = ResearchController(
        artifact_store=InMemoryArtifactStore(),
        artifact_content_store=InMemoryArtifactContentStore(),
    )
    artifact_id = "evidence-candidate-1"
    controller.artifact_store.put(
        ArtifactRef(
            artifact_id=artifact_id,
            project_id="output-demo",
            artifact_type="EvidenceMatrixCandidate",
            version=1,
            content_uri=f"artifact-content://output-demo/{artifact_id}/1",
            sha256="a" * 64,
            created_at=datetime.now(UTC),
            created_by="evidence_review",
        )
    )
    controller.artifact_content_store.put(
        ArtifactContent(
            project_id="output-demo",
            artifact_id=artifact_id,
            version=1,
            artifact_type="EvidenceMatrixCandidate",
            schema_version="v1",
            body={
                "title": "迁移能力证据矩阵",
                "evidence_refs": ["evidence-1"],
            },
        )
    )
    controller.agent_plan_store.put(
        AgentExecutionPlan(
            plan_id="plan-output-demo",
            project_id="output-demo",
            conversation_id="conversation-output",
            turn_id="turn-output",
            user_request="整理证据",
            intent_summary="本轮将处理：文献证据",
            status=AgentPlanStatus.COMPLETED,
            tasks=[
                AgentTaskPlan(
                    task_id="task-evidence",
                    agent_id="evidence_review",
                    task_type="synthesize_evidence",
                    reason="整理证据",
                    expected_output_types=["EvidenceMatrixCandidate"],
                    status=AgentTaskStatus.COMPLETED,
                    output_refs=["candidate://evidence_review/EvidenceMatrixCandidate"],
                    persisted_artifact_ids=[artifact_id],
                    evidence_refs=["evidence-1"],
                )
            ],
        )
    )

    outputs = controller.list_agent_outputs("output-demo")
    assert len(outputs) == 1
    assert outputs[0].target_pages == ["knowledge_evidence", "evidence_gate"]
    assert outputs[0].output_previews[0].content["title"] == "迁移能力证据矩阵"
    assert outputs[0].output_previews[0].researcher_summary.startswith("迁移能力证据矩阵")
    assert outputs[0].output_previews[0].summary_mode == "deterministic"
    assert controller.list_agent_outputs("output-demo", conversation_id="other") == []
    assert len(controller.list_agent_outputs("output-demo", turn_id="turn-output")) == 1

    decision = controller.decide_agent_output(
        "output-demo",
        artifact_id,
        AgentOutputDecisionRequest(decision="retain", decided_by="researcher"),
    )
    assert decision["formalization"] == "project_material"
    assert controller.artifact_store.get("output-demo", artifact_id).status == "RETAINED"

    applied = controller.decide_agent_output(
        "output-demo",
        artifact_id,
        AgentOutputDecisionRequest(
            decision="apply",
            decided_by="researcher",
            target="knowledge_evidence",
        ),
    )
    assert applied["target"] == "knowledge_evidence"
    materials = controller.list_agent_page_materials(
        "output-demo", target="knowledge_evidence"
    )
    assert len(materials) == 1
    assert materials[0].artifact_id == artifact_id
    assert materials[0].plan_id == "plan-output-demo"


def test_evidence_output_promotion_is_blocked_without_verified_source_snapshot() -> None:
    controller = ResearchController(
        artifact_store=InMemoryArtifactStore(),
        artifact_content_store=InMemoryArtifactContentStore(),
    )
    artifact_id = "unverified-evidence-candidate"
    controller.artifact_store.put(
        ArtifactRef(
            artifact_id=artifact_id,
            project_id="formal-demo",
            artifact_type="EvidenceMatrixCandidate",
            version=1,
            content_uri=f"artifact-content://formal-demo/{artifact_id}/1",
            sha256="b" * 64,
            created_at=datetime.now(UTC),
            created_by="evidence_review",
        )
    )
    controller.artifact_content_store.put(
        ArtifactContent(
            project_id="formal-demo",
            artifact_id=artifact_id,
            version=1,
            artifact_type="EvidenceMatrixCandidate",
            schema_version="v1",
            body={
                "title": "待核验证据矩阵",
                "evidence_refs": ["evidence-1"],
            },
        )
    )

    decision = controller.decide_agent_output(
        "formal-demo",
        artifact_id,
        AgentOutputDecisionRequest(decision="promote", decided_by="researcher"),
    )

    assert decision["formalization"] == "candidate_evidence_only"
    assert decision["risk_flags"] == ["FORMAL_EVIDENCE_MISSING_SOURCE_SNAPSHOT"]
    assert controller.artifact_store.get("formal-demo", artifact_id).status == "REVIEW_REQUIRED"


def test_evidence_promotion_requires_a_stable_source_chunk_reference() -> None:
    controller = ResearchController(
        artifact_store=InMemoryArtifactStore(),
        artifact_content_store=InMemoryArtifactContentStore(),
    )
    artifact_id = "missing-chunk-reference"
    controller.artifact_store.put(
        ArtifactRef(
            artifact_id=artifact_id,
            project_id="formal-chunk-demo",
            artifact_type="EvidenceMatrixCandidate",
            version=1,
            content_uri=f"artifact-content://formal-chunk-demo/{artifact_id}/1",
            sha256="c" * 64,
            created_at=datetime.now(UTC),
            created_by="evidence_review",
        )
    )
    controller.artifact_content_store.put(
        ArtifactContent(
            project_id="formal-chunk-demo",
            artifact_id=artifact_id,
            version=1,
            artifact_type="EvidenceMatrixCandidate",
            schema_version="v1",
            body={
                "evidence_refs": ["evidence-1"],
                "evidence_snapshot": [{
                    "evidence_id": "evidence-1",
                    "project_id": "formal-chunk-demo",
                    "verification_status": "source_verified",
                    "location": {"chunk_index": 4, "char_start": 20, "char_end": 80},
                }],
            },
        )
    )

    decision = controller.decide_agent_output(
        "formal-chunk-demo",
        artifact_id,
        AgentOutputDecisionRequest(decision="promote", decided_by="researcher"),
    )

    assert decision["risk_flags"] == ["FORMAL_EVIDENCE_MISSING_SOURCE_CHUNK_REF"]


def test_evidence_fallback_deduplicates_typed_candidate_artifacts() -> None:
    agent = EvidenceReviewAgent()
    context = ContextBundle(
        context_id="ctx-evidence-dedup",
        project_id="evidence-dedup-demo",
        task_ref="task-evidence-dedup",
        query="牛顿第二定律与物理建模",
        evidence_refs=[
            EvidenceRef(
                evidence_id="evidence-dedup-1",
                project_id="evidence-dedup-demo",
                source_id="source-1",
                chunk_id="chunk-1",
                excerpt="模型需要明确系统边界和受力关系。",
                location=SourceLocation(chunk_index=2, char_start=10, char_end=28),
                verification_status=VerificationStatus.SOURCE_VERIFIED,
            )
        ],
        source_refs=["source-1"],
        unresolved_questions=[],
        risk_flags=[],
        verification_summary={"source_verified": 1},
        token_budget=500,
        estimated_tokens=20,
        context_hash="d" * 64,
        generated_at=datetime.now(UTC),
    )
    agent_input = AgentInput(
        agent_run_id="evidence-dedup-run",
        task_ref="task-evidence-dedup",
        context_bundle_ref="ctx-evidence-dedup",
        allowed_tool_capabilities=list(agent.allowed_tool_capabilities),
        allowed_output_types=list(agent.allowed_output_types),
        policy_version="v1",
        prompt_template_version="evidence-v1",
    )

    result = agent._deterministic_result(agent_input, context)
    refs = [artifact.candidate_ref for artifact in result.candidate_artifacts]

    assert len(refs) == len(set(refs))
    matrix = next(
        artifact
        for artifact in result.candidate_artifacts
        if artifact.artifact_type == "EvidenceMatrixCandidate"
    )
    assert matrix.body["evidence_snapshot"]

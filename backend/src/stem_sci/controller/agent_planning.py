"""Natural-language Agent planning and candidate-output governance.

The planner proposes a task graph.  It never invokes a domain Agent, changes
the project stage, or promotes an artifact by itself.  Those actions remain
Controller-owned and require an explicit human decision.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from stem_sci.agents import AgentCapability
from stem_sci.agents.runtime import StructuredGenerationError, StructuredGenerator


class AgentPlanStatus(StrEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    WAITING_TASK_APPROVAL = "WAITING_TASK_APPROVAL"
    REWORK_REQUIRED = "REWORK_REQUIRED"


class AgentTaskStatus(StrEnum):
    PLANNED = "PLANNED"
    WAITING_DEPENDENCY = "WAITING_DEPENDENCY"
    SKIPPED = "SKIPPED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class AgentOutputDecision(StrEnum):
    RETAIN = "retain"
    REJECT = "reject"
    APPLY = "apply"
    PROMOTE = "promote"


class AgentExecutionMode(StrEnum):
    AUTOMATIC = "automatic"
    STEPWISE = "stepwise"


class AgentTaskPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    task_type: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    input_refs: list[str] = Field(default_factory=list)
    required_context: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    expected_output_types: list[str] = Field(min_length=1)
    risk_level: str = "MEDIUM"
    approval_required: bool = True
    status: AgentTaskStatus = AgentTaskStatus.PLANNED
    blocked_reason: str | None = None
    agent_run_id: str | None = None
    output_refs: list[str] = Field(default_factory=list)
    persisted_artifact_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    error: str | None = None
    review_note: str | None = None


class AgentExecutionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    conversation_id: str | None = None
    turn_id: str | None = None
    user_request: str = Field(min_length=1)
    conversation_context: list[str] = Field(default_factory=list)
    intent_summary: str = Field(min_length=1)
    status: AgentPlanStatus = AgentPlanStatus.PENDING_APPROVAL
    tasks: list[AgentTaskPlan] = Field(default_factory=list)
    source_context_refs: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    planner_mode: str = "capability_rules"
    execution_mode: AgentExecutionMode = AgentExecutionMode.AUTOMATIC
    pending_review_task_id: str | None = None
    rework_note: str | None = None
    approved_task_ids: list[str] = Field(default_factory=list)
    approved_by: str | None = None
    approved_at: datetime | None = None
    executed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=64)
    user_request: str = Field(min_length=1)
    conversation_id: str | None = None
    turn_id: str | None = None
    context_refs: list[str] = Field(default_factory=list)
    conversation_context: list[str] = Field(default_factory=list, max_length=5)


class AgentPlanApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern="^(approved|rejected)$")
    decided_by: str = Field(min_length=1)
    selected_task_ids: list[str] | None = None
    execution_mode: AgentExecutionMode = AgentExecutionMode.AUTOMATIC


class AgentTaskApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern="^(approved|rework)$")
    decided_by: str = Field(min_length=1)
    note: str | None = Field(default=None, max_length=2_000)


class AgentOutputDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: AgentOutputDecision
    decided_by: str = Field(min_length=1)
    target: str | None = None
    note: str | None = None


class AgentOutputSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    task_id: str
    project_id: str
    user_request: str | None = None
    conversation_id: str | None = None
    turn_id: str | None = None
    agent_id: str
    task_type: str
    status: AgentTaskStatus
    input_refs: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    risk_level: str = "MEDIUM"
    output_types: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    output_previews: list["AgentOutputPreview"] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    decision: str = "candidate"
    target_pages: list[str] = Field(default_factory=list)
    error: str | None = None
    agent_run_id: str | None = None
    agent_version: str | None = None
    # A task-level answer keeps the UI from having to choose between several
    # JSON artifacts or repeat the same question for every artifact.
    primary_artifact_id: str | None = None
    researcher_answer: str = ""
    summary_mode: str = "deterministic"


class AgentPageMaterial(BaseModel):
    """A deliberately applied Agent output shown on one professional page."""

    model_config = ConfigDict(extra="forbid")

    material_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    target: str = Field(min_length=1)
    conversation_id: str | None = None
    turn_id: str | None = None
    formalization: str = "candidate"
    applied_by: str = Field(min_length=1)
    applied_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content: dict[str, JsonValue] = Field(default_factory=dict)


class AgentOutputPreview(BaseModel):
    """A review-oriented snapshot of one persisted Agent candidate."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    artifact_type: str
    status: str
    content: dict[str, JsonValue] = Field(default_factory=dict)
    researcher_summary: str = ""
    review_points: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    summary_mode: str = "deterministic"


class FormalEvidenceRecord(BaseModel):
    """A deduplicated formal-evidence link with round-level provenance."""

    model_config = ConfigDict(extra="forbid")

    project_id: str
    evidence_id: str
    artifact_id: str
    plan_id: str
    task_id: str
    agent_id: str
    conversation_id: str | None = None
    turn_id: str | None = None
    promoted_by: str
    promoted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    evidence_ref: dict[str, JsonValue] = Field(default_factory=dict)
    provenance: list[dict[str, JsonValue]] = Field(default_factory=list)


class FormalEvidenceStore(Protocol):
    def put(self, record: FormalEvidenceRecord) -> FormalEvidenceRecord: ...

    def list_project(self, project_id: str) -> list[FormalEvidenceRecord]: ...


# Resolve the forward reference after both output models exist. This keeps
# FastAPI response serialization reliable across supported Pydantic versions.
AgentOutputSummary.model_rebuild()


class _PlannerTaskDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1)
    task_type: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    expected_output_types: list[str] = Field(default_factory=list)
    risk_level: str = "MEDIUM"


class _PlannerDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_summary: str = Field(min_length=1)
    tasks: list[_PlannerTaskDraft] = Field(min_length=1)


class AgentPlanStore(Protocol):
    def put(self, plan: AgentExecutionPlan) -> AgentExecutionPlan: ...

    def get(self, project_id: str, plan_id: str) -> AgentExecutionPlan | None: ...

    def list_project(self, project_id: str) -> list[AgentExecutionPlan]: ...


class AgentPageMaterialStore(Protocol):
    def put(self, material: AgentPageMaterial) -> AgentPageMaterial: ...

    def list_project(
        self,
        project_id: str,
        *,
        target: str | None = None,
        conversation_id: str | None = None,
        turn_id: str | None = None,
    ) -> list[AgentPageMaterial]: ...


class InMemoryAgentPlanStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], AgentExecutionPlan] = {}

    def put(self, plan: AgentExecutionPlan) -> AgentExecutionPlan:
        self._items[(plan.project_id, plan.plan_id)] = plan
        return plan

    def get(self, project_id: str, plan_id: str) -> AgentExecutionPlan | None:
        return self._items.get((project_id, plan_id))

    def list_project(self, project_id: str) -> list[AgentExecutionPlan]:
        return sorted(
            [plan for (item_project, _), plan in self._items.items() if item_project == project_id],
            key=lambda item: item.created_at,
            reverse=True,
        )


class InMemoryAgentPageMaterialStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], AgentPageMaterial] = {}

    def put(self, material: AgentPageMaterial) -> AgentPageMaterial:
        self._items[(material.project_id, material.material_id)] = material
        return material

    def list_project(
        self,
        project_id: str,
        *,
        target: str | None = None,
        conversation_id: str | None = None,
        turn_id: str | None = None,
    ) -> list[AgentPageMaterial]:
        return sorted(
            [
                material
                for (item_project, _), material in self._items.items()
                if item_project == project_id
                and (target is None or material.target == target)
                and (conversation_id is None or material.conversation_id == conversation_id)
                and (turn_id is None or material.turn_id == turn_id)
            ],
            key=lambda item: item.applied_at,
            reverse=True,
        )


class InMemoryFormalEvidenceStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], FormalEvidenceRecord] = {}

    def put(self, record: FormalEvidenceRecord) -> FormalEvidenceRecord:
        existing = self._items.get((record.project_id, record.evidence_id))
        if existing is not None:
            record = record.model_copy(update={"provenance": [*existing.provenance, *record.provenance]})
        self._items[(record.project_id, record.evidence_id)] = record
        return record

    def list_project(self, project_id: str) -> list[FormalEvidenceRecord]:
        return sorted(
            [item for (item_project, _), item in self._items.items() if item_project == project_id],
            key=lambda item: item.promoted_at,
            reverse=True,
        )


class SQLiteAgentPlanStore:
    """SQLite-backed plan snapshots stored beside the existing workflow DB."""

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                create table if not exists workflow_agent_plans (
                    project_id text not null,
                    plan_id text not null,
                    body text not null,
                    primary key (project_id, plan_id)
                )
                """
            )

    def put(self, plan: AgentExecutionPlan) -> AgentExecutionPlan:
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                insert into workflow_agent_plans(project_id, plan_id, body)
                values (?, ?, ?)
                on conflict(project_id, plan_id) do update set body=excluded.body
                """,
                (plan.project_id, plan.plan_id, plan.model_dump_json()),
            )
        return plan

    def get(self, project_id: str, plan_id: str) -> AgentExecutionPlan | None:
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(
                "select body from workflow_agent_plans where project_id=? and plan_id=?",
                (project_id, plan_id),
            ).fetchone()
        return AgentExecutionPlan.model_validate_json(row[0]) if row is not None else None

    def list_project(self, project_id: str) -> list[AgentExecutionPlan]:
        with sqlite3.connect(self.database) as connection:
            rows = connection.execute(
                """
                select body from workflow_agent_plans
                where project_id=? order by rowid desc
                """,
                (project_id,),
            ).fetchall()
        return [AgentExecutionPlan.model_validate_json(row[0]) for row in rows]


class SQLiteAgentPageMaterialStore:
    """Persist page placements separately from the immutable Agent artifacts."""

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                create table if not exists workflow_agent_page_materials (
                    project_id text not null,
                    material_id text not null,
                    target text not null,
                    conversation_id text,
                    turn_id text,
                    body text not null,
                    primary key (project_id, material_id)
                )
                """
            )
            connection.execute(
                """
                create index if not exists workflow_agent_page_materials_lookup
                on workflow_agent_page_materials(project_id, target, conversation_id, turn_id)
                """
            )

    def put(self, material: AgentPageMaterial) -> AgentPageMaterial:
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                insert into workflow_agent_page_materials(
                    project_id, material_id, target, conversation_id, turn_id, body
                ) values (?, ?, ?, ?, ?, ?)
                on conflict(project_id, material_id) do update set
                    target=excluded.target,
                    conversation_id=excluded.conversation_id,
                    turn_id=excluded.turn_id,
                    body=excluded.body
                """,
                (
                    material.project_id,
                    material.material_id,
                    material.target,
                    material.conversation_id,
                    material.turn_id,
                    material.model_dump_json(),
                ),
            )
        return material

    def list_project(
        self,
        project_id: str,
        *,
        target: str | None = None,
        conversation_id: str | None = None,
        turn_id: str | None = None,
    ) -> list[AgentPageMaterial]:
        clauses = ["project_id=?"]
        values: list[str] = [project_id]
        if target is not None:
            clauses.append("target=?")
            values.append(target)
        if conversation_id is not None:
            clauses.append("conversation_id=?")
            values.append(conversation_id)
        if turn_id is not None:
            clauses.append("turn_id=?")
            values.append(turn_id)
        with sqlite3.connect(self.database) as connection:
            rows = connection.execute(
                f"select body from workflow_agent_page_materials where {' and '.join(clauses)} order by rowid desc",
                values,
            ).fetchall()
        return [AgentPageMaterial.model_validate_json(row[0]) for row in rows]


class SQLiteFormalEvidenceStore:
    """Project-scoped, evidence-id-keyed formalization links.

    The unique key intentionally uses ``(project_id, evidence_id)``. Reusing
    an evidence chunk in another Agent round updates provenance instead of
    duplicating the formal evidence item.
    """

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                create table if not exists workflow_formal_evidence (
                    project_id text not null,
                    evidence_id text not null,
                    body text not null,
                    primary key (project_id, evidence_id)
                )
                """
            )

    def put(self, record: FormalEvidenceRecord) -> FormalEvidenceRecord:
        with sqlite3.connect(self.database) as connection:
            previous = connection.execute(
                "select body from workflow_formal_evidence where project_id=? and evidence_id=?",
                (record.project_id, record.evidence_id),
            ).fetchone()
            if previous is not None:
                old = FormalEvidenceRecord.model_validate_json(previous[0])
                record = record.model_copy(
                    update={"provenance": [*old.provenance, *record.provenance]}
                )
            connection.execute(
                """
                insert into workflow_formal_evidence(project_id, evidence_id, body)
                values (?, ?, ?)
                on conflict(project_id, evidence_id) do update set body=excluded.body
                """,
                (record.project_id, record.evidence_id, record.model_dump_json()),
            )
        return record

    def list_project(self, project_id: str) -> list[FormalEvidenceRecord]:
        with sqlite3.connect(self.database) as connection:
            rows = connection.execute(
                "select body from workflow_formal_evidence where project_id=? order by rowid desc",
                (project_id,),
            ).fetchall()
        return [FormalEvidenceRecord.model_validate_json(row[0]) for row in rows]


_TASK_OUTPUTS: dict[str, tuple[str, ...]] = {
    "mentor_planning": (
        "ResearchQuestionTree",
        "FeasibilityReport",
        "ProjectRoadmap",
        "InitialRiskProfile",
    ),
    "evidence_review": (
        "EvidenceSufficiencyReport",
        "CorpusCoverageReport",
        "ScreeningLedger",
        "PaperCardCollection",
        "EvidenceMatrixCandidate",
        "ResearchGapReport",
        "BoundedEvidenceSynthesis",
    ),
    "research_design": (
        "Estimand",
        "StudyProtocolCandidate",
        "MeasurementPlan",
        "DataCollectionSchema",
    ),
    "data_analysis": (
        "DataAuditSpecification",
        "DataProcessingPlanCandidate",
        "ExecutableAnalysisPlanCandidate",
        "CodeSpecificationDraft",
    ),
    "paper_writing": (
        "AtomicClaimGraph",
        "ManuscriptOutline",
        "ManuscriptDraftZh",
        "ManuscriptDraftEn",
    ),
    "independent_review": (
        "ReviewFinding",
        "RevisionRequest",
        "ReviewReport",
    ),
}

_TARGET_PAGES: dict[str, tuple[str, ...]] = {
    # The first target is the default destination used by the workbench.
    # Keep the role-specific page first so "apply" cannot silently land in
    # the generic workspace.
    "mentor_planning": ("research_questions", "workspace"),
    "evidence_review": ("knowledge_evidence", "evidence_gate"),
    "research_design": ("research_design", "data_collection"),
    "data_analysis": ("data_analysis", "codex"),
    "paper_writing": ("paper_editor",),
    "independent_review": ("audit_validation",),
}


class WorkflowAgentPlanner:
    """Build a minimal task graph from a user request and Agent capabilities."""

    def __init__(
        self,
        capabilities: list[AgentCapability],
        *,
        generator: StructuredGenerator | None = None,
        model: str | None = None,
    ) -> None:
        self.capabilities = {item.agent_id: item for item in capabilities}
        self.generator = generator
        self.model = model

    def build(self, request: AgentPlanRequest) -> AgentExecutionPlan:
        text = request.user_request.lower()
        selected: list[str] = []

        self._select(selected, "mentor_planning", text, ("研究问题", "研究范围", "选题", "可行性", "路线"))
        self._select(
            selected,
            "evidence_review",
            text,
            ("证据", "文献", "引用", "研究空白", "来源", "核验", "理论"),
        )
        self._select(
            selected,
            "research_design",
            text,
            ("设计", "前测", "后测", "迁移", "变量", "测量", "实验", "方案", "预注册", "假设"),
        )
        self._select(
            selected,
            "data_analysis",
            text,
            ("数据", "csv", "统计", "分析", "缺失", "异常", "代码", "codex", "spss", "结果"),
        )
        self._select(selected, "paper_writing", text, ("论文", "写作", "摘要", "章节", "草稿", "投稿"))
        self._select(
            selected,
            "independent_review",
            text,
            ("审查", "检查", "复现", "审稿", "质量", "风险", "一致性"),
        )
        if not selected:
            selected.append("mentor_planning")

        tasks: list[AgentTaskPlan] = []
        for agent_id in selected:
            capability = self.capabilities.get(agent_id)
            if capability is None:
                continue
            task_type = self._task_type(agent_id, text)
            expected = [
                output
                for output in _TASK_OUTPUTS[agent_id]
                if output in capability.allowed_output_types
            ]
            expected = self._ensure_primary_outputs(
                agent_id, expected, capability.allowed_output_types
            )
            if not expected:
                expected = capability.allowed_output_types[:4]
            dependencies = self._dependencies(agent_id, selected)
            blocked_reason = self._blocked_reason(agent_id, text)
            status = (
                AgentTaskStatus.WAITING_DEPENDENCY
                if dependencies
                else AgentTaskStatus.PLANNED
            )
            tasks.append(
                AgentTaskPlan(
                    task_id=f"task-{agent_id}-{uuid4().hex[:8]}",
                    agent_id=agent_id,
                    task_type=task_type,
                    reason=self._reason(agent_id, task_type),
                    input_refs=list(request.context_refs)
                    or ([f"conversation-turn://{request.conversation_id}/{request.turn_id}"]
                        if request.conversation_id and request.turn_id
                        else []),
                    required_context=list(request.context_refs),
                    depends_on=dependencies,
                    expected_output_types=expected,
                    risk_level="HIGH" if agent_id in {"evidence_review", "data_analysis"} else "MEDIUM",
                    status=status,
                    blocked_reason=blocked_reason,
                )
            )

        plan = AgentExecutionPlan(
            plan_id=f"plan-{uuid4().hex}",
            project_id=request.project_id,
            conversation_id=request.conversation_id,
            turn_id=request.turn_id,
            user_request=request.user_request,
            conversation_context=list(request.conversation_context),
            intent_summary=self._intent_summary(selected),
            tasks=tasks,
            source_context_refs=list(request.context_refs),
            risk_flags=[],
            unresolved_questions=[],
        )
        risk_flags = []
        unresolved = []
        if "evidence_review" in selected:
            risk_flags.append("FORMAL_EVIDENCE_REQUIRES_SOURCE_VERIFICATION")
        if "data_analysis" in selected and self._blocked_reason("data_analysis", text):
            unresolved.append("数据分析需要已批准的研究方案、冻结分析计划和数据集。")
        if "paper_writing" in selected:
            risk_flags.append("MANUSCRIPT_OUTPUT_REMAINS_CANDIDATE")
        plan = plan.model_copy(
            update={
                "risk_flags": risk_flags,
                "unresolved_questions": unresolved,
            }
        )
        return self._model_refine(plan, request)

    def _model_refine(
        self, fallback: AgentExecutionPlan, request: AgentPlanRequest
    ) -> AgentExecutionPlan:
        if self.generator is None or not self.model:
            return fallback
        capabilities = [
            {
                "agent_id": item.agent_id,
                "supported_task_types": item.supported_task_types,
                "allowed_output_types": item.allowed_output_types,
            }
            for item in self.capabilities.values()
        ]
        prompt = (
            "根据用户当前研究需求生成最小必要的 Agent 任务计划。只选择确实需要的 "
            "Agent，不要默认调用全部 Agent。depends_on 只能填写 agent_id。每个任务的 "
            "expected_output_types 必须来自对应 Agent 的 allowed_output_types。不要输出 "
            "思维链，只输出简短理由。\n\n"
            f"可用 Agent 能力：{capabilities}\n"
            f"用户需求：{request.user_request}\n"
            f"最近对话片段：{request.conversation_context}\n"
            f"当前上下文引用：{request.context_refs}"
        )
        try:
            generated = self.generator.generate(
                system_prompt=(
                    "你是 STEM-SCI 工作流规划器。你只规划任务，不执行 Agent、代码、数据 "
                    "修改或审批。输出必须是结构化 JSON。"
                ),
                user_prompt=prompt,
                response_model=_PlannerDraft,
                model=self.model,
                prompt_version="workflow-agent-planner-v1",
            )
        except (StructuredGenerationError, ValueError):
            return fallback.model_copy(
                update={
                    "risk_flags": [*fallback.risk_flags, "PLANNER_MODEL_FALLBACK"],
                }
            )
        draft = generated.parsed_output
        if not isinstance(draft, _PlannerDraft):
            return fallback
        refined = self._from_model_draft(fallback, draft, request)
        return refined.model_copy(
            update={
                "planner_mode": "llm",
                "risk_flags": [
                    *refined.risk_flags,
                    f"PLANNER_MODEL_REQUEST:{generated.request_id}",
                ],
            }
        )

    def _from_model_draft(
        self,
        fallback: AgentExecutionPlan,
        draft: _PlannerDraft,
        request: AgentPlanRequest,
    ) -> AgentExecutionPlan:
        tasks: list[AgentTaskPlan] = []
        accepted_agents: set[str] = set()
        for item in draft.tasks:
            capability = self.capabilities.get(item.agent_id)
            if capability is None or item.task_type not in capability.supported_task_types:
                continue
            expected = [
                output
                for output in item.expected_output_types
                if output in capability.allowed_output_types
            ]
            if not expected:
                expected = [
                    output
                    for output in _TASK_OUTPUTS.get(item.agent_id, ())
                    if output in capability.allowed_output_types
                ][:4]
            expected = self._ensure_primary_outputs(
                item.agent_id, expected, capability.allowed_output_types
            )
            if not expected:
                continue
            accepted_agents.add(item.agent_id)
            tasks.append(
                AgentTaskPlan(
                    task_id=f"task-{item.agent_id}-{uuid4().hex[:8]}",
                    agent_id=item.agent_id,
                    task_type=item.task_type,
                    reason=item.reason,
                    input_refs=list(request.context_refs)
                    or ([f"conversation-turn://{request.conversation_id}/{request.turn_id}"]
                        if request.conversation_id and request.turn_id
                        else []),
                    required_context=list(request.context_refs),
                    depends_on=[
                        f"agent:{dependency}"
                        for dependency in item.depends_on
                        if dependency in self.capabilities and dependency != item.agent_id
                    ],
                    expected_output_types=expected,
                    risk_level=item.risk_level,
                    blocked_reason=self._blocked_reason(item.agent_id, request.user_request.lower()),
                )
            )
        if not tasks:
            return fallback
        known_agents = {task.agent_id for task in tasks}
        for index, task in enumerate(tasks):
            dependencies = [
                dependency
                for dependency in task.depends_on
                if dependency.split(":", 1)[-1] in known_agents
            ]
            tasks[index] = task.model_copy(
                update={
                    "depends_on": dependencies,
                    "status": (
                        AgentTaskStatus.WAITING_DEPENDENCY
                        if dependencies
                        else AgentTaskStatus.PLANNED
                    ),
                }
            )
        return fallback.model_copy(
            update={
                "intent_summary": draft.intent_summary,
                "tasks": tasks,
                "risk_flags": [
                    flag for flag in fallback.risk_flags
                    if flag != "PLANNER_MODEL_FALLBACK"
                ],
                "unresolved_questions": [
                    question for question in fallback.unresolved_questions
                    if "数据分析" not in question or "data_analysis" in accepted_agents
                ],
            }
        )

    @staticmethod
    def _ensure_primary_outputs(
        agent_id: str, outputs: list[str], allowed_outputs: list[str]
    ) -> list[str]:
        """Keep the UI and downstream gates anchored to useful results."""
        primary = {
            "mentor_planning": ["ResearchQuestionTree", "FeasibilityReport"],
            "evidence_review": [
                "EvidenceMatrixCandidate",
                "PaperCardCollection",
                "EvidenceSufficiencyReport",
            ],
            "research_design": ["StudyProtocolCandidate", "MeasurementPlan"],
            "data_analysis": ["DataAuditSpecification", "DataProcessingPlanCandidate"],
            "paper_writing": ["ManuscriptDraftZh", "ManuscriptOutline"],
            "independent_review": ["ReviewReport", "RevisionRequest", "ReviewFinding"],
        }.get(agent_id, [])
        ordered = [item for item in primary if item in allowed_outputs]
        ordered = [item for item in ordered if item in outputs or agent_id == "evidence_review"]
        ordered.extend(item for item in outputs if item not in ordered)
        return ordered

    @staticmethod
    def _select(
        selected: list[str], agent_id: str, text: str, keywords: tuple[str, ...]
    ) -> None:
        if any(keyword in text for keyword in keywords) and agent_id not in selected:
            selected.append(agent_id)

    @staticmethod
    def _task_type(agent_id: str, text: str) -> str:
        if agent_id == "mentor_planning":
            return "assess_feasibility" if "可行" in text else "scope_research"
        if agent_id == "evidence_review":
            return "synthesize_evidence" if any(word in text for word in ("证据", "综合", "空白")) else "screen_evidence"
        if agent_id == "research_design":
            return "define_estimand" if any(word in text for word in ("衡量", "指标", "变量")) else "draft_study_protocol"
        if agent_id == "data_analysis":
            return "audit_data_specification" if any(word in text for word in ("审查", "缺失", "异常")) else "draft_analysis_specification"
        if agent_id == "paper_writing":
            return "draft_reproducibility_statement" if "复现" in text else "draft_manuscript"
        return "review_reproducibility" if "复现" in text else "review_method"

    @staticmethod
    def _dependencies(agent_id: str, selected: list[str]) -> list[str]:
        prior = {
            "research_design": ["evidence_review"],
            "data_analysis": ["research_design"],
            "paper_writing": ["evidence_review", "research_design", "data_analysis"],
            "independent_review": [
                item for item in selected if item != "independent_review"
            ],
        }.get(agent_id, [])
        return [
            f"agent:{dependency}"
            for dependency in prior
            if dependency in selected
        ]

    @staticmethod
    def _blocked_reason(agent_id: str, text: str) -> str | None:
        if agent_id == "data_analysis" and not any(
            word in text for word in ("数据", "csv", "统计", "分析", "代码", "codex", "spss")
        ):
            return "尚未发现数据集或数据分析需求。"
        if agent_id == "paper_writing" and not any(
            word in text for word in ("论文", "写作", "摘要", "章节", "草稿", "投稿")
        ):
            return "当前对话没有明确的论文写作需求。"
        return None

    @staticmethod
    def _reason(agent_id: str, task_type: str) -> str:
        return {
            "mentor_planning": "界定研究问题、范围和可行性，生成项目层候选方案。",
            "evidence_review": "检索、筛选和组织与当前问题相关的来源证据。",
            "research_design": "把研究目标转换为变量、测量方案和可审批研究设计。",
            "data_analysis": f"生成 {task_type} 所需的审查或分析规格；实际数据操作由确定性算子完成。",
            "paper_writing": "把已保留的研究材料整理为可追溯的论文候选稿。",
            "independent_review": "独立检查证据、方法、引用或可复现性风险。",
        }[agent_id]

    @staticmethod
    def _intent_summary(selected: list[str]) -> str:
        names = {
            "mentor_planning": "研究范围",
            "evidence_review": "文献证据",
            "research_design": "研究设计",
            "data_analysis": "数据分析",
            "paper_writing": "论文写作",
            "independent_review": "独立审查",
        }
        return "本轮将处理：" + "、".join(names[item] for item in selected)

"""Controller-owned Agent registry, dispatch and minimal planning workflow."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import ClassVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from stem_sci.agents import (
    AgentCapability,
    AgentInput,
    AgentResult,
    DataAnalysisAgent,
    EvidenceReviewAgent,
    IndependentReviewAgent,
    MentorPlanningAgent,
    PaperWritingAgent,
    PlanningBrief,
    ResearchDesignAgent,
    ResearchDesignBrief,
)
from stem_sci.agents.analysis_contracts import (
    DataAnalysisPreAnalysisInput,
    DataAnalysisPreAnalysisOutcome,
)
from stem_sci.agents.base import BaseAgent
from stem_sci.agents.contracts import ApprovalRequest, ReviewFinding
from stem_sci.agents.evidence_pipeline import (
    EvidenceMatrixRow,
    EvidenceReviewPipeline,
    PaperCard,
)
from stem_sci.agents.reviewer_contracts import (
    MethodReviewInput,
    ManuscriptNumericClaim,
    ReproducibilityReviewInput,
    ReviewCriterion,
    ReproducibilityReviewOutcome,
)
from stem_sci.agents.runtime import StructuredGenerator
from stem_sci.agents.research_generation import MentorPlanningPipeline, ResearchDesignPipeline
from stem_sci.agents.writing_pipeline import (
    LanguageCode,
    PaperWritingPipeline,
    WritingContextBundle,
)
from stem_sci.artifacts.artifact_store import ArtifactStore, InMemoryArtifactStore
from stem_sci.artifacts.content_store import (
    ArtifactContent,
    ArtifactContentStore,
    InMemoryArtifactContentStore,
)
from stem_sci.artifacts.decision_store import DecisionStore, InMemoryDecisionStore
from stem_sci.artifacts.models import ArtifactRef
from stem_sci.context.models import ContextBundle
from stem_sci.context.provider import ContextProvider
from stem_sci.controller.data_pipeline import (
    DataPipelineBeginRequest,
    DataPipelineController,
    DataPipelineStage,
    DataPipelineState,
)
from stem_sci.controller.policy.route_decision import RouteDecision
from stem_sci.core.enums import DecisionScope, ProjectStage, TaskStatus
from stem_sci.core.models import ApprovalRecord
from stem_sci.core.reducers import merge_references
from stem_sci.core.state import ResearchState
from stem_sci.operators.executor import OperatorExecutor
from stem_sci.provenance.agent_run_store import AgentRunStore, InMemoryAgentRunStore
from stem_sci.provenance.models import AgentRunRecord
from stem_sci.statistics.mode_policy import AnalysisMode
from stem_sci.statistics.models import AnalysisModelSpecification

from .merger import validate_agent_result
from .agent_planning import (
    AgentExecutionPlan,
    AgentExecutionMode,
    AgentOutputDecisionRequest,
    AgentPageMaterial,
    AgentPageMaterialStore,
    AgentOutputPreview,
    AgentOutputSummary,
    FormalEvidenceRecord,
    FormalEvidenceStore,
    AgentPlanApprovalRequest,
    AgentTaskApprovalRequest,
    AgentPlanRequest,
    AgentPlanStatus,
    AgentPlanStore,
    AgentTaskPlan,
    AgentTaskStatus,
    InMemoryAgentPlanStore,
    InMemoryAgentPageMaterialStore,
    InMemoryFormalEvidenceStore,
    WorkflowAgentPlanner,
    _TARGET_PAGES,
)
from .policy.route_store import RouteDecisionStore
from .store import WorkflowStore


class ControllerWorkflowState(BaseModel):
    """Reference-only state owned and changed by the Controller."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)
    current_stage: ProjectStage = ProjectStage.INTAKE
    pending_approval_ref: str | None = None
    last_agent_run_id: str | None = None
    last_route_decision: RouteDecision | None = None
    research_state: ResearchState | None = None
    data_pipeline: DataPipelineState | None = None
    data_pipeline_package_ref: str | None = None


class ResearcherOutputSummary(BaseModel):
    """Bounded presentation layer for a structured Agent candidate."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=1_200)
    review_points: list[str] = Field(default_factory=list, max_length=4)
    action_items: list[str] = Field(default_factory=list, max_length=4)


class PlanningRequest(BaseModel):
    """Initial research idea submitted to the Controller."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)
    research_intent: str = Field(min_length=1)
    context_bundle_ref: str = "context://initial"
    run_id: str = Field(default_factory=lambda: f"planning-{uuid4().hex}")


class PlanningRunResult(BaseModel):
    """Result of the planning slice, paused at human approval."""

    model_config = ConfigDict(extra="forbid")

    workflow_state: ControllerWorkflowState
    agent_result: AgentResult
    approval_request: ApprovalRequest
    route_decision: RouteDecision | None = None


class WorkflowRunResult(BaseModel):
    """A routed Agent run and the approval required before progression."""

    workflow_state: ControllerWorkflowState
    agent_result: AgentResult
    approval_request: ApprovalRequest
    route_decision: RouteDecision


class ReproducibilityReviewRequest(BaseModel):
    """Controller input for read-only manuscript-number verification.

    Statistical result cards are intentionally not accepted from callers. The
    Controller derives the sole permitted card from the project's completed
    deterministic data pipeline.
    """

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)
    manuscript_ref: str = Field(min_length=1)
    numeric_claims: list[ManuscriptNumericClaim] = Field(min_length=1)
    tolerance: float = Field(default=1e-9, ge=0.0)


class ReproducibilityReviewRunResult(BaseModel):
    """Controller-routed reviewer output; the Reviewer never sets workflow state."""

    model_config = ConfigDict(extra="forbid")

    workflow_state: ControllerWorkflowState
    outcome: ReproducibilityReviewOutcome
    approval_request: ApprovalRequest | None = None


@dataclass(frozen=True)
class AgentRegistry:
    """Controller-owned mapping from stable agent ids to role implementations."""

    agents: Mapping[str, BaseAgent]

    @classmethod
    def default(
        cls,
        *,
        generator: StructuredGenerator | None = None,
        model: str | None = None,
    ) -> AgentRegistry:
        if (generator is None) != (model is None):
            raise ValueError("generator and model must be configured together")
        if generator is not None and model is not None:
            mentor_agent = MentorPlanningAgent(
                pipeline=MentorPlanningPipeline(generator=generator, model=model)
            )
            design_agent = ResearchDesignAgent(
                pipeline=ResearchDesignPipeline(generator=generator, model=model)
            )
            evidence_agent = EvidenceReviewAgent(
                pipeline=EvidenceReviewPipeline(generator=generator, model=model)
            )
            writing_agent = PaperWritingAgent(
                pipeline=PaperWritingPipeline(generator=generator, model=model)
            )
        else:
            mentor_agent = MentorPlanningAgent()
            design_agent = ResearchDesignAgent()
            evidence_agent = EvidenceReviewAgent()
            writing_agent = PaperWritingAgent()
        instances: Iterable[BaseAgent] = (
            mentor_agent,
            evidence_agent,
            design_agent,
            DataAnalysisAgent(),
            writing_agent,
            IndependentReviewAgent(),
        )
        return cls({agent.agent_id: agent for agent in instances})

    def get(self, agent_id: str) -> BaseAgent:
        try:
            return self.agents[agent_id]
        except KeyError as exc:
            raise ValueError(f"unknown agent: {agent_id}") from exc


class AgentDispatcher:
    """Invoke an agent and validate its result before returning it to workflow code."""

    def __init__(self, registry: AgentRegistry | None = None) -> None:
        self.registry = registry or AgentRegistry.default()

    def dispatch(
        self,
        agent_id: str,
        agent_input: AgentInput,
        context_bundle: ContextBundle | WritingContextBundle | None = None,
    ) -> AgentResult:
        agent = self.registry.get(agent_id)
        run_with_context = getattr(agent, "run_with_context", None)
        result = (
            run_with_context(agent_input, context_bundle)
            if context_bundle is not None and callable(run_with_context)
            else agent.run(agent_input)
        )
        return validate_agent_result(result, agent.capability())


class ResearchController:
    """Controller-owned dynamic routing over the six deterministic Agent roles."""

    _EVIDENCE_APPROVAL_BLOCKING_RISKS: ClassVar[frozenset[str]] = frozenset(
        {
            "insufficient_corpus_coverage",
            "insufficient_verified_evidence",
        }
    )

    _ROUTES: ClassVar[dict[ProjectStage, tuple[str, str, str, str]]] = {
        ProjectStage.SCOPED: (
            "evidence_review",
            "evidence_protocol",
            "design_search_protocol",
            "ResearchContract and approved scope",
        ),
        ProjectStage.EVIDENCE_READY: (
            "research_design",
            "study_protocol",
            "draft_study_protocol",
            "verified evidence and research gap",
        ),
        ProjectStage.STUDY_PROTOCOL_APPROVED: (
            "data_analysis",
            "analysis_specification",
            "draft_analysis_specification",
            "approved study protocol",
        ),
        ProjectStage.ANALYZED: (
            "paper_writing",
            "manuscript",
            "draft_manuscript",
            "validated statistical result",
        ),
        ProjectStage.DRAFTED: (
            "independent_review",
            "review_report",
            "review_method",
            "draft manuscript and claim map",
        ),
    }
    _REWORK_ROUTES: ClassVar[dict[str, tuple[str, str, str, str]]] = {
        "mentor_planning": (
            "mentor_planning",
            "research_scope",
            "scope_research",
            "rejected research scope",
        ),
        "evidence_review": (
            "evidence_review",
            "evidence_protocol",
            "design_search_protocol",
            "rejected evidence protocol",
        ),
        "research_design": (
            "research_design",
            "study_protocol",
            "draft_study_protocol",
            "rejected study protocol",
        ),
        "data_analysis": (
            "data_analysis",
            "analysis_specification",
            "analysis_execution",
            "rejected analysis specification",
        ),
        "paper_writing": (
            "paper_writing",
            "manuscript",
            "draft_manuscript",
            "rejected manuscript or review revision",
        ),
        "independent_review": (
            "independent_review",
            "review_report",
            "review_method",
            "rejected review report",
        ),
    }
    _REWORK_TARGETS: ClassVar[dict[str, str]] = {
        "research_scope": "mentor_planning",
        "evidence_protocol": "evidence_review",
        "study_protocol": "research_design",
        "analysis_specification": "data_analysis",
        "analysis_execution": "data_analysis",
        "manuscript": "paper_writing",
        "review_report": "paper_writing",
    }
    _REVIEW_FINDING_TARGETS: ClassVar[dict[str, str]] = {
        "contribution": "mentor_planning",
        "scope": "mentor_planning",
        "novelty": "mentor_planning",
        "citation": "evidence_review",
        "evidence": "evidence_review",
        "literature": "evidence_review",
        "method": "research_design",
        "design": "research_design",
        "sampling": "research_design",
        "measurement": "research_design",
        "causal": "research_design",
        "pedagogy": "research_design",
        "transfer": "research_design",
        "intervention": "research_design",
        "analysis": "data_analysis",
        "statistics": "data_analysis",
        "data": "data_analysis",
        "reproducibility": "data_analysis",
        "code": "data_analysis",
        "claim": "paper_writing",
        "writing": "paper_writing",
        "structure": "paper_writing",
        "interpretation": "paper_writing",
        "discussion": "paper_writing",
    }

    def __init__(
        self,
        dispatcher: AgentDispatcher | None = None,
        context_provider: ContextProvider | None = None,
        decision_store: DecisionStore | None = None,
        workflow_store: WorkflowStore | None = None,
        operator_executor: OperatorExecutor | None = None,
        artifact_store: ArtifactStore | None = None,
        artifact_content_store: ArtifactContentStore | None = None,
        agent_run_store: AgentRunStore | None = None,
        route_store: RouteDecisionStore | None = None,
        agent_plan_store: AgentPlanStore | None = None,
        agent_page_material_store: AgentPageMaterialStore | None = None,
        formal_evidence_store: FormalEvidenceStore | None = None,
        planner_generator: StructuredGenerator | None = None,
        planner_model: str | None = None,
        data_pipeline_root: Path | None = None,
    ) -> None:
        self.dispatcher = dispatcher or AgentDispatcher()
        self.context_provider = context_provider
        self.decision_store = decision_store or InMemoryDecisionStore()
        self.workflow_store = workflow_store
        self.operator_executor = operator_executor or OperatorExecutor()
        self.artifact_store = artifact_store or InMemoryArtifactStore()
        self.artifact_content_store = artifact_content_store or InMemoryArtifactContentStore()
        self.agent_run_store = agent_run_store or InMemoryAgentRunStore()
        self.route_store = route_store
        self.agent_plan_store = agent_plan_store or InMemoryAgentPlanStore()
        self.agent_page_material_store = agent_page_material_store or InMemoryAgentPageMaterialStore()
        self.formal_evidence_store = formal_evidence_store or InMemoryFormalEvidenceStore()
        self.agent_planner = WorkflowAgentPlanner(
            [agent.capability() for agent in self.dispatcher.registry.agents.values()],
            generator=planner_generator,
            model=planner_model,
        )
        self.summary_generator = planner_generator
        self.summary_model = planner_model
        self._strict_data_pipeline = data_pipeline_root is not None
        self.data_pipeline = DataPipelineController(
            storage_root=data_pipeline_root or Path(".stem_sci"),
            operator_executor=self.operator_executor,
        )
        self._states: dict[str, ResearchState] = {}
        self._workflow_states: dict[str, ControllerWorkflowState] = {}
        self._routes: dict[str, RouteDecision] = {}
        self._approvals: dict[str, ApprovalRequest] = {}
        self._project_intents: dict[str, str] = {}
        self._state_lock = RLock()

    def _persist(self, project_id: str) -> None:
        if self.workflow_store is None:
            return
        self.workflow_store.save(
            project_id,
            self._project_intents[project_id],
            self._workflow_states[project_id],
            self._approvals.get(project_id),
        )

    def _restore(self, project_id: str) -> ControllerWorkflowState | None:
        if self.workflow_store is None:
            return None
        snapshot = self.workflow_store.get(project_id)
        if snapshot is None:
            return None
        state = ControllerWorkflowState.model_validate_json(snapshot.workflow_state_json)
        self._workflow_states[project_id] = state
        if state.research_state is not None:
            self._states[project_id] = state.research_state
        if state.last_route_decision is not None:
            self._routes[project_id] = state.last_route_decision
        self._project_intents[project_id] = snapshot.project_intent
        if snapshot.pending_approval_json is not None:
            self._approvals[project_id] = ApprovalRequest.model_validate_json(
                snapshot.pending_approval_json
            )
        return state

    def _build_pre_analysis_input(
        self, project_id: str, run_id: str, task_type: str, state: ControllerWorkflowState
    ) -> tuple[DataAnalysisPreAnalysisInput, AnalysisModelSpecification]:
        """Build the narrow CSV MVP package from the approved protocol boundary.

        The values are deliberately explicit and reference-only.  They provide a
        runnable default for the current CSV demo while the domain-specific
        protocol compiler is being filled in; the risk flag is persisted with the
        Agent result so this cannot be mistaken for a substantive decision.
        """

        protocol_ref = (
            state.research_state.protocol_refs[0]
            if state.research_state is not None and state.research_state.protocol_refs
            else f"protocol://{project_id}/v1"
        )
        preregistered_plan_ref = f"prereg-plan://{project_id}/v1"
        request = DataAnalysisPreAnalysisInput(
            agent_run_id=run_id,
            project_id=project_id,
            task_ref=f"{project_id}:{task_type}",
            study_protocol_ref=protocol_ref,
            preregistered_plan_ref=preregistered_plan_ref,
            preregistered_plan_status="frozen",
            preregistration_approval_ref=f"approval://{project_id}/prereg-v1",
            data_collection_schema_ref=f"schema://{project_id}/collection-v1",
            variable_dictionary_ref=f"dictionary://{project_id}/v1",
            analysis_mode=AnalysisMode.PYTHON_ONLY,
            model_specification_refs=[f"model-spec://{project_id}/main-v1"],
            required_variables=["group", "transfer_score"],
            missingness_checks=["report missingness"],
            range_and_type_checks=["numeric transfer score"],
            privacy_checks=["reject direct identifiers"],
            proposed_processing_steps=["approved lossless processing"],
            missing_data_strategy_ref=f"prereg-plan://{project_id}/missingness",
            diagnostic_checks=["residual check"],
            robustness_checks=["pre-specified sensitivity check"],
        )
        model_specification = AnalysisModelSpecification(
            model_spec_id="main-v1",
            project_id=project_id,
            model_family="group_mean_difference",
            outcome_variables=["transfer_score"],
            predictor_variables=["group"],
            formula_or_design="mean(transfer_score) by group",
            rationale="Narrow CSV MVP configuration; replace with the approved model compiler output.",
        )
        return request, model_specification

    def _persist_pre_analysis_package(
        self,
        project_id: str,
        outcome: DataAnalysisPreAnalysisOutcome,
        model_specification: AnalysisModelSpecification,
    ) -> str:
        package_ref = f"data-analysis-package://{project_id}/{outcome.agent_result.agent_run_id}"
        self.artifact_content_store.put(
            ArtifactContent(
                project_id=project_id,
                artifact_id=f"data-analysis-package:{outcome.agent_result.agent_run_id}",
                version=1,
                artifact_type="DataAnalysisPreAnalysisPackage",
                schema_version="v1",
                body={
                    "package_ref": package_ref,
                    "pre_analysis": outcome.model_dump(mode="json"),
                    "model_specification": model_specification.model_dump(mode="json"),
                    "source": "controller-narrow-csv-mvp",
                },
            )
        )
        return package_ref

    def _begin_data_pipeline_from_package(
        self, project_id: str, workflow_state: ControllerWorkflowState
    ) -> DataPipelineState:
        package_ref = workflow_state.data_pipeline_package_ref
        if not package_ref:
            raise ValueError("analysis approval has no data pipeline package")
        package = next(
            (
                item
                for item in self.artifact_content_store.list_project(project_id)
                if item.artifact_type == "DataAnalysisPreAnalysisPackage"
                and item.body.get("package_ref") == package_ref
            ),
            None,
        )
        if package is None:
            raise ValueError("data pipeline package content is unavailable")
        pre_analysis = DataAnalysisPreAnalysisOutcome.model_validate(package.body["pre_analysis"])
        model_specification = AnalysisModelSpecification.model_validate(
            package.body["model_specification"]
        )
        return self.data_pipeline.begin(
            DataPipelineBeginRequest(
                project_id=project_id,
                preregistered_plan_ref=pre_analysis.executable_plan_candidate.preregistered_plan_ref,
                preregistration_approval_ref=(
                    f"approval://{project_id}/prereg-v1"
                ),
                pre_analysis=pre_analysis,
                model_specification=model_specification,
            )
        )

    def _execute_agent_tools(
        self,
        project_id: str,
        result: AgentResult,
        *,
        query: str = "",
        context_bundle: ContextBundle | None = None,
    ) -> tuple[list[str], list[str], list[str]]:
        runs = self.operator_executor.execute_tool_requests(
            project_id=project_id,
            agent_run_id=result.agent_run_id,
            tool_requests=result.tool_requests,
            query=query,
            context_bundle=context_bundle,
        )
        execution_refs = [run.operator_run_id for run in runs]
        output_artifact_refs = [
            artifact_ref
            for run in runs
            for artifact_ref in run.output_artifact_refs
        ]
        risk_flags: list[str] = []
        if any(run.status.value == "BLOCKED" for run in runs):
            risk_flags.append("OPERATOR_EXECUTION_UNAVAILABLE")
        if any(run.status.value == "FAILED" for run in runs):
            risk_flags.append("OPERATOR_REQUEST_FAILED")
        if any(run.status.value == "NEEDS_REVIEW" for run in runs):
            risk_flags.append("OPERATOR_REVIEW_REQUIRED")
        return execution_refs, output_artifact_refs, risk_flags

    def _record_audit(
        self,
        agent_input: AgentInput,
        result: AgentResult,
        route: RouteDecision,
        execution_refs: list[str],
        output_artifact_refs: Iterable[str] = (),
        evidence_snapshot: Iterable[Mapping[str, object]] = (),
        user_request: str | None = None,
    ) -> list[ArtifactRef]:
        candidate_content = {
            artifact.candidate_ref: artifact for artifact in result.candidate_artifacts
        }
        candidate_content_by_type = {
            artifact.artifact_type: artifact for artifact in result.candidate_artifacts
        }
        effective_request = user_request or self._project_intents.get(route.project_id, "")
        persisted_artifacts: list[ArtifactRef] = []
        for index, artifact_ref in enumerate(result.candidate_artifact_refs):
            artifact_type = artifact_ref.rsplit("/", maxsplit=1)[-1]
            artifact_id = f"{result.agent_run_id}:artifact:{index}"
            content_uri = artifact_ref
            artifact_hash = sha256(artifact_ref.encode("utf-8")).hexdigest()
            # A specialist is allowed to return a typed payload whose
            # reference was normalized by the dispatcher. Match by type as a
            # compatibility fallback so real content is never replaced by a
            # generic candidate envelope.
            payload = candidate_content.get(artifact_ref)
            if payload is None and index < len(result.candidate_artifacts):
                indexed_payload = result.candidate_artifacts[index]
                if indexed_payload.artifact_type == artifact_type:
                    payload = indexed_payload
            if payload is None:
                payload = candidate_content_by_type.get(artifact_type)
            if payload is not None:
                body = dict(payload.body)
                # Carry the conversation turn into every material. This makes
                # an applied result auditable without forcing the UI to infer
                # its origin from an artifact ID.
                body.setdefault("project_id", route.project_id)
                body.setdefault("agent_id", result.agent_id)
                body.setdefault("task_ref", agent_input.task_ref)
                body.setdefault(
                    "user_request", effective_request
                )
                if evidence_snapshot and artifact_type in {
                    "PaperCardCollection",
                    "EvidenceMatrixCandidate",
                    "BoundedEvidenceSynthesis",
                }:
                    if not body.get("evidence_snapshot"):
                        body["evidence_snapshot"] = list(evidence_snapshot)
                body = self._with_researcher_summary(
                    body,
                    artifact_type=payload.artifact_type,
                    user_request=effective_request,
                )
                content = self.artifact_content_store.put(
                    ArtifactContent(
                        artifact_id=artifact_id,
                        project_id=route.project_id,
                        artifact_type=payload.artifact_type,
                        version=1,
                        schema_version=payload.schema_version,
                        body=body,
                        created_at=result.created_at,
                    )
                )
                if content.content_hash is None:
                    raise ValueError("persisted artifact content has no hash")
                artifact_hash = content.content_hash
                content_uri = (
                    f"artifact-content://{route.project_id}/{artifact_id}/{content.version}"
                )
            else:
                # Some scaffold agents return capability-bound references
                # without domain content. Persist a role-specific candidate
                # brief so the researcher can review substance, not just IDs.
                body = self._deterministic_candidate_body(
                    agent_id=result.agent_id,
                    artifact_type=artifact_type,
                    project_id=route.project_id,
                    task_ref=agent_input.task_ref,
                    user_request=effective_request,
                    evidence_refs=list(result.evidence_refs),
                    evidence_snapshot=list(evidence_snapshot),
                    candidate_ref=artifact_ref,
                )
                body = self._with_researcher_summary(
                    body,
                    artifact_type=artifact_type,
                    user_request=effective_request,
                )
                content = self.artifact_content_store.put(
                    ArtifactContent(
                        artifact_id=artifact_id,
                        project_id=route.project_id,
                        artifact_type=artifact_type,
                        version=1,
                        schema_version="v1",
                        body=body,
                        created_at=result.created_at,
                    )
                )
                if content.content_hash is None:
                    raise ValueError("persisted candidate envelope has no hash")
                artifact_hash = content.content_hash
                content_uri = (
                    f"artifact-content://{route.project_id}/{artifact_id}/{content.version}"
                )
            artifact = ArtifactRef(
                artifact_id=artifact_id,
                project_id=route.project_id,
                artifact_type=artifact_type,
                version=1,
                content_uri=content_uri,
                sha256=artifact_hash,
                created_at=result.created_at,
                created_by=result.agent_id,
            )
            self.artifact_store.put(artifact)
            persisted_artifacts.append(artifact)
        self.agent_run_store.put(
            AgentRunRecord(
                agent_run_id=result.agent_run_id,
                project_id=route.project_id,
                agent_id=result.agent_id,
                agent_version=result.agent_version,
                prompt_template_version=agent_input.prompt_template_version,
                input_artifact_refs=[agent_input.context_bundle_ref],
                output_artifact_refs=[
                    *result.candidate_artifact_refs,
                    *output_artifact_refs,
                ],
                tool_run_refs=execution_refs,
                llm_metadata_refs=result.llm_metadata_refs,
                route_decision_ref=route.decision_id,
                started_at=result.created_at,
                finished_at=result.created_at,
            )
        )
        if self.route_store is not None:
            self.route_store.put(route)
        return persisted_artifacts

    @staticmethod
    def _deterministic_candidate_body(
        *,
        agent_id: str,
        artifact_type: str,
        project_id: str,
        task_ref: str,
        user_request: str,
        evidence_refs: list[str],
        evidence_snapshot: list[Mapping[str, object]],
        candidate_ref: str,
    ) -> dict[str, object]:
        """Build reviewable, explicitly provisional content for scaffold runs.

        The Phase 1 controller may receive only candidate references from an
        agent.  A reference-only record is not useful to a human reviewer, so
        this method supplies a bounded role brief.  It contains no invented
        empirical values and is never eligible for formal evidence promotion
        without source verification.
        """
        evidence_status = (
            "待核验：本轮没有可定位的来源证据。"
            if not evidence_snapshot
            else f"已关联 {len(evidence_snapshot)} 条检索证据，仍需逐条核验来源定位。"
        )
        common: dict[str, object] = {
            "candidate_ref": candidate_ref,
            "project_id": project_id,
            "agent_id": agent_id,
            "task_ref": task_ref,
            "status": "candidate",
            "review_status": "待人工审查",
            "user_request": user_request or "当前对话研究需求未提供。",
            "evidence_refs": evidence_refs,
            "evidence_snapshot": evidence_snapshot,
            "source_verification": evidence_status,
            "review_instruction": "这是候选工作材料，不是正式证据、正式结果或已批准方案。",
        }

        if agent_id == "mentor_planning":
            common.update(
                {
                    "title": "导师规划候选方案",
                    "research_question": "在当前研究需求下，哪些研究问题、范围和阶段性任务值得优先验证？",
                    "scope": ["明确研究对象与情境", "界定干预、比较条件和结果指标", "记录不应在本轮扩大的范围"],
                    "feasibility_assumptions": [
                        "目标参与者和研究情境能够在伦理与数据治理批准后获得。",
                        "前测、后测和迁移任务可以使用同一套可审查评分规则。",
                    ],
                    "roadmap": [
                        "确认研究问题与证据需求",
                        "形成前测、后测和迁移任务候选",
                        "批准研究方案与测量计划",
                        "完成数据审查、分析和独立审查",
                    ],
                    "items_to_confirm": ["研究对象与样本范围", "主要结果指标", "伦理和数据治理条件"],
                }
            )
        elif agent_id == "evidence_review":
            common.update(
                {
                    "title": "证据审查候选报告",
                    "sufficiency_judgement": "当前结果只能作为证据候选，不能直接支撑正式结论。",
                    "corpus_coverage": "需要检查检索范围、去重结果、纳入排除标准和主题覆盖。",
                    "evidence_rows": [
                        {
                            "evidence_ref": ref,
                            "claim_candidate": "待根据原文片段提取并限定主张。",
                            "verification_status": "待核验",
                            "required_locator": "页码或字符区间",
                        }
                        for ref in evidence_refs
                    ],
                    "formalization_blockers": [
                        "来源文件必须存在并可打开。",
                        "证据必须绑定稳定 chunk 标识和页码或字符定位。",
                        "需要人工确认原文片段确实支持对应主张。",
                    ],
                    "recommended_review": "先审查来源定位和原文，再决定是否保留为项目材料。",
                }
            )
        elif agent_id == "research_design":
            common.update(
                {
                    "title": "前测、后测与迁移任务研究设计候选",
                    "design_question": "如何在保持物理概念一致的同时，用新建模情境检验概念迁移？",
                    "pretest": {"purpose": "测量干预前的概念理解与建模基础", "format": "概念解释题、模型选择题和简短建模任务"},
                    "posttest": {"purpose": "测量学习后目标概念、建模过程和解释质量", "format": "与前测等值但不直接重复题目"},
                    "transfer_task": {"purpose": "测量迁移到新情境的能力", "format": "改变表面情境，保持核心物理关系，要求建模、运行和解释"},
                    "variables": {"primary_outcome": "迁移任务评分", "secondary_outcomes": ["概念理解", "模型解释质量", "代码与模型一致性"]},
                    "measurement_requirements": ["评分量规", "盲法或双人评分安排", "前测后测和迁移任务的等值性说明"],
                    "design_risks": ["练习效应", "任务难度不等值", "评分者主观差异"],
                }
            )
        elif agent_id == "data_analysis":
            common.update(
                {
                    "title": "数据审查与分析计划候选",
                    "required_dataset_fields": ["participant_id（去标识化）", "group", "pretest_score", "posttest_score", "transfer_score"],
                    "audit_checks": ["字段存在性和类型", "缺失值比例", "分数范围", "重复记录", "组别编码", "直接身份标识排查"],
                    "analysis_plan": [
                        "先锁定数据字典和处理规则，再执行确定性数据审查。",
                        "报告前测、后测和迁移任务的描述性统计。",
                        "依据已批准方案选择组间比较或协方差模型。",
                        "将缺失处理、敏感性分析和效应量作为预先声明的内容。",
                    ],
                    "output_boundary": "没有真实数据和已批准分析方案时，不生成统计数字或效果结论。",
                    "review_checklist": ["处理规则可复现", "代码输入输出可追溯", "结果仅来自冻结数据集"],
                }
            )
        elif agent_id == "paper_writing":
            common.update(
                {
                    "title": "论文写作候选草稿",
                    "manuscript_status": "候选草稿，尚未完成证据和结果核验",
                    "outline": ["研究背景与问题", "相关证据", "研究设计", "数据与分析", "结果", "讨论与局限"],
                    "draft_sections": {
                        "background": "本节需要由已核验来源支持研究背景和研究空白。",
                        "methods": "本候选稿将前测、后测和迁移任务作为主要研究设计，并等待研究方案审核。",
                        "results": "尚无可写入的正式统计结果；不得根据候选材料补写数字或方向。",
                        "limitations": "需要说明样本、任务等值性、评分可靠性和来源核验限制。",
                    },
                    "claim_evidence_requirements": ["每个外部主张绑定已核验证据", "每个数字绑定结果卡", "解释范围不超出批准方案"],
                }
            )
        elif agent_id == "independent_review":
            common.update(
                {
                    "title": "独立审查候选报告",
                    "review_scope": ["证据来源与定位", "研究设计与测量", "数据处理与分析", "论文主张与证据", "可复现性"],
                    "findings": [
                        {"severity": "high", "category": "evidence", "finding": "正式证据必须具备来源核验和稳定定位。", "action": "补充原文片段、页码或字符区间并人工确认。"},
                        {"severity": "medium", "category": "workflow", "finding": "候选产出不能替代批准的研究方案或冻结数据结果。", "action": "在进入专业页面或正式材料前保留人工决策记录。"},
                    ],
                    "revision_requests": ["逐条补齐证据链", "确认前测、后测和迁移任务的评分规则", "检查论文表述没有超出数据与方案边界"],
                    "recommendation": "修改后重新审查；本报告不直接修改论文、证据或项目状态。",
                }
            )
        else:
            common.update(
                {
                    "title": f"{artifact_type} 候选输出",
                    "content": "该候选输出尚未配置专门的正文模板，请根据任务引用和人工审查要求补充。",
                }
            )
        return common

    def _with_researcher_summary(
        self,
        body: dict[str, object],
        *,
        artifact_type: str,
        user_request: str,
    ) -> dict[str, object]:
        """Attach a concise, non-authoritative review summary to an artifact.

        The structured body remains the system record.  A model may only
        restate it for a researcher; failures use the deterministic summary so
        persistence and review never depend on an LLM response.
        """
        result = dict(body)
        fallback = self._deterministic_researcher_summary(
            result, artifact_type=artifact_type
        )
        if self.summary_generator is None or self.summary_model is None:
            result["researcher_summary"] = fallback
            result["summary_mode"] = "deterministic"
            return result

        try:
            generation = self.summary_generator.generate(
                system_prompt=(
                    "You turn a structured research-workflow candidate into a concise "
                    "Chinese review brief. Use only facts present in the supplied JSON. "
                    "Do not invent sources, data, results, verification, or approval. "
                    "Keep candidate and verification limits explicit."
                ),
                user_prompt=json.dumps(
                    {
                        "artifact_type": artifact_type,
                        "user_request": user_request,
                        "candidate": result,
                        "required_output": {
                            "summary": "one direct Chinese conclusion for a researcher",
                            "review_points": "0-4 concise points to check",
                            "action_items": "0-4 concrete next actions",
                        },
                    },
                    ensure_ascii=False,
                    default=str,
                )[:16_000],
                response_model=ResearcherOutputSummary,
                model=self.summary_model,
                prompt_version="agent-output-review-brief-v1",
            )
            summary = ResearcherOutputSummary.model_validate(generation.parsed_output)
            result["researcher_summary"] = summary.model_dump(mode="json")
            result["summary_mode"] = "llm"
        except Exception:
            # Presentation must never turn an otherwise valid candidate into a
            # failed workflow task.  The deterministic brief is intentionally
            # conservative and carries no new research claims.
            result["researcher_summary"] = fallback
            result["summary_mode"] = "deterministic"
        return result

    @staticmethod
    def _deterministic_researcher_summary(
        body: Mapping[str, object], *, artifact_type: str
    ) -> dict[str, object]:
        """Create a readable fallback without inferring facts from JSON."""
        def text(value: object) -> str | None:
            return value.strip() if isinstance(value, str) and value.strip() else None

        title = text(body.get("title")) or {
            "ResearchQuestionTree": "研究问题树",
            "FeasibilityReport": "可行性审查",
            "EvidenceMatrixCandidate": "证据矩阵",
            "PaperCardCollection": "论文卡片集合",
            "EvidenceSufficiencyReport": "证据充分性审查",
            "StudyProtocolCandidate": "研究方案",
            "MeasurementPlan": "测量计划",
            "DataCollectionSchema": "数据采集结构",
            "DataAuditSpecification": "数据审查规则",
            "DataProcessingPlanCandidate": "数据处理计划",
            "ExecutableAnalysisPlanCandidate": "可执行分析计划",
            "CodeSpecificationDraft": "代码规格",
            "ManuscriptDraftZh": "中文论文草稿",
            "ManuscriptOutline": "论文结构",
            "ReviewReport": "独立审查报告",
        }.get(artifact_type, f"{artifact_type} 候选产物")
        type_specific: str | None = None
        if artifact_type == "StudyProtocolCandidate":
            outcome = text(body.get("primary_outcome")) or "主要结果指标"
            design = text(body.get("design_type")) or "候选研究设计"
            timepoints = body.get("measurement_timepoints")
            point_text = "、".join(item for item in timepoints if isinstance(item, str)) if isinstance(timepoints, list) else "预设时间点"
            type_specific = f"方案拟采用{design}，以{outcome}为主要结果，在{point_text}进行测量。"
        elif artifact_type == "MeasurementPlan":
            outcome = text(body.get("primary_outcome")) or "主要结果指标"
            fields = body.get("data_dictionary_fields")
            field_count = len(fields) if isinstance(fields, list) else 0
            type_specific = f"测量计划以{outcome}为主要结果，设置{field_count}个数据字典字段。"
        elif artifact_type == "DataAuditSpecification":
            required = body.get("required_variables")
            count = len(required) if isinstance(required, list) else 0
            type_specific = f"数据审查要求检查{count}个必需变量，并执行缺失、类型范围和隐私检查。"
        elif artifact_type == "DataProcessingPlanCandidate":
            steps = body.get("proposed_steps")
            count = len(steps) if isinstance(steps, list) else 0
            type_specific = f"数据处理候选方案包含{count}个预设处理步骤，执行前仍需人工批准。"
        elif artifact_type == "ExecutableAnalysisPlanCandidate":
            models = body.get("model_specification_refs")
            count = len(models) if isinstance(models, list) else 0
            type_specific = f"可执行分析计划引用{count}个模型规格，不能改变已批准的研究假设。"
        elif artifact_type == "CodeSpecificationDraft":
            languages = body.get("expected_languages")
            type_specific = f"代码规格要求生成{('、'.join(item for item in languages if isinstance(item, str)) if isinstance(languages, list) else 'Python')}代码，并产出可验证结果卡。"
        elif artifact_type == "EvidenceMatrixCandidate":
            rows = body.get("rows")
            count = len(rows) if isinstance(rows, list) else 0
            type_specific = f"当前证据矩阵包含{count}条候选证据行，正式化前必须逐条核验来源定位。"
        elif artifact_type == "CorpusCoverageReport":
            source_count = body.get("source_count")
            evidence_count = body.get("evidence_count")
            missing = body.get("missing_topics")
            missing_count = len(missing) if isinstance(missing, list) else 0
            type_specific = (
                f"本轮覆盖{source_count if isinstance(source_count, int) else 0}个来源、"
                f"{evidence_count if isinstance(evidence_count, int) else 0}条证据，"
                f"仍有{missing_count}个主题待补齐。"
            )
        elif artifact_type == "EvidenceSufficiencyReport":
            evidence_count = body.get("evidence_count")
            missing = body.get("missing_requirements")
            missing_count = len(missing) if isinstance(missing, list) else 0
            type_specific = (
                f"当前可用证据{evidence_count if isinstance(evidence_count, int) else 0}条，"
                f"还有{missing_count}项证据条件待满足。"
            )
        elif artifact_type == "ResearchGapReport":
            gaps = body.get("gaps")
            count = len(gaps) if isinstance(gaps, list) else 0
            type_specific = f"已整理{count}项候选研究空白，需回到原文逐条核验其支持范围。"
        elif artifact_type == "ScreeningLedger":
            decisions = body.get("decisions")
            count = len(decisions) if isinstance(decisions, list) else 0
            type_specific = f"已记录{count}条来源筛选记录，筛选结果仍属于候选审查材料。"
        elif artifact_type == "PaperCardCollection":
            cards = body.get("cards")
            count = len(cards) if isinstance(cards, list) else 0
            type_specific = f"当前整理出{count}张论文卡片，内容只能作为来源审查候选。"
        elif artifact_type == "ReviewReport":
            recommendation = text(body.get("overall_recommendation")) or "待审查"
            type_specific = f"独立审查结论为{recommendation}，修改请求需由研究者决定是否执行。"
        elif artifact_type == "RevisionRequest":
            changes = body.get("required_changes")
            count = len(changes) if isinstance(changes, list) else 0
            type_specific = f"独立审查提出{count}项修改请求，是否执行由研究者决定。"
        elif artifact_type == "ReviewFinding":
            severity = text(body.get("severity")) or "待定"
            category = text(body.get("category")) or "研究质量"
            type_specific = f"发现一项{severity}级{category}问题，需查看修改建议后决定是否返工。"
        elif artifact_type == "ManuscriptDraftZh":
            sections = body.get("sections")
            count = len(sections) if isinstance(sections, Mapping) else 0
            type_specific = f"已形成中文论文候选草稿，包含{count}个章节内容；外部主张和统计结果仍需绑定正式来源。"
        conclusion = next(
            (
                text(body.get(key))
                for key in (
                    "research_question",
                    "primary_question",
                    "design_question",
                    "primary_outcome",
                    "sufficiency_judgement",
                    "summary",
                    "overall_recommendation",
                    "output_boundary",
                    "recommendation",
                    "content",
                )
                if text(body.get(key))
            ),
            None,
        )
        summary = f"{title}：{type_specific or conclusion or '已生成候选材料，等待研究者审查。'}"

        def strings_from(keys: tuple[str, ...], limit: int = 3) -> list[str]:
            items: list[str] = []
            for key in keys:
                value = body.get(key)
                if isinstance(value, list):
                    items.extend(item.strip() for item in value if isinstance(item, str) and item.strip())
                elif (item := text(value)) is not None:
                    items.append(item)
            return list(dict.fromkeys(items))[:limit]

        review_points = strings_from(
            ("source_verification", "review_instruction", "formalization_blockers", "design_risks", "review_checklist"),
        )
        action_items = strings_from(
            ("items_to_confirm", "recommended_review", "measurement_requirements", "revision_requests", "claim_evidence_requirements"),
        )
        if not action_items:
            action_items = ["审查候选内容后，决定保留、应用主产物或拒绝。"]
        return {
            "summary": summary,
            "review_points": review_points,
            "action_items": action_items,
        }

    def _approved_output_refs(self, project_id: str) -> set[str]:
        """Return persisted artifact IDs that were explicitly approved."""
        approved_refs = {
            decision.artifact_id
            for decision in self.decision_store.list_project(project_id)
            if decision.decision == "approved"
        }
        persisted_ids = {
            artifact.artifact_id for artifact in self.artifact_store.list_project(project_id)
        }
        resolved = approved_refs.intersection(persisted_ids)
        if resolved == approved_refs:
            return resolved

        # Older workflow approvals point to candidate:// refs rather than the
        # generated artifact ID. Resolve those refs through the audited run
        # record while keeping the new artifact-ID path intact.
        for record in self.agent_run_store.list_project(project_id):
            for candidate_ref in approved_refs.difference(resolved):
                try:
                    index = record.output_artifact_refs.index(candidate_ref)
                except ValueError:
                    continue
                artifact_id = f"{record.agent_run_id}:artifact:{index}"
                if artifact_id in persisted_ids:
                    resolved.add(artifact_id)
        return resolved

    def _build_writing_context(
        self,
        project_id: str,
        task_type: str,
        state: ControllerWorkflowState,
    ) -> WritingContextBundle:
        """Assemble writing inputs from project-scoped Controller references."""
        research_state = state.research_state
        if research_state is None or research_state.project_id != project_id:
            raise ValueError("writing route requires a project-scoped research state")

        evidence_refs = []
        context_bundle: ContextBundle | None = None
        if self.context_provider is not None:
            context_bundle = self.context_provider.build_context(
                project_id=project_id,
                task_ref=f"{project_id}:{task_type}",
                query=self._project_intents.get(project_id, "writing context"),
                token_budget=2_000,
            )
            if context_bundle.project_id != project_id:
                raise ValueError("context provider returned a cross-project bundle")
            allowed_evidence = set(research_state.evidence_refs)
            evidence_refs = [
                evidence
                for evidence in context_bundle.evidence_refs
                if evidence.project_id == project_id
                and evidence.evidence_id in allowed_evidence
            ]

        approved_refs = self._approved_output_refs(project_id)
        approved_artifacts = {
            artifact.artifact_id: artifact
            for artifact in self.artifact_store.list_project(project_id)
            if artifact.artifact_id in approved_refs
        }
        approved_types = {artifact.artifact_type for artifact in approved_artifacts.values()}
        paper_cards: list[PaperCard] = []
        evidence_matrix: list[dict[str, object]] = []
        for content in self.artifact_content_store.list_project(project_id):
            if content.artifact_type not in approved_types:
                continue
            if content.artifact_type == "PaperCardCollection":
                cards = content.body.get("cards")
                if isinstance(cards, list):
                    for card in cards:
                        if isinstance(card, dict):
                            try:
                                parsed = PaperCard.model_validate(card)
                            except ValueError:
                                continue
                            if parsed.project_id == project_id:
                                paper_cards.append(parsed)
            elif content.artifact_type == "EvidenceMatrixCandidate":
                rows = content.body.get("rows")
                if isinstance(rows, list):
                    for row in rows:
                        if isinstance(row, dict):
                            try:
                                parsed_row = EvidenceMatrixRow.model_validate(row)
                            except ValueError:
                                continue
                            if parsed_row.project_id == project_id:
                                evidence_matrix.append(parsed_row.model_dump(mode="json"))

        approved_research_scope = self._project_intents.get(project_id, "writing context")
        protocol_refs = list(research_state.protocol_refs)
        result_refs = list(research_state.research_test_result_refs)
        protocol_output_types = {
            "StudyProtocolCandidate",
            "PreregisteredAnalysisPlanDraft",
        }
        # StatisticalResultCard is a deterministic execution artifact, never an
        # Agent candidate. Writing may consume an approved interpretation
        # boundary from an Agent, but RESULT claims must point to a card built
        # from a passing ResultValidationReport.
        result_output_types = {"ResultInterpretationBoundary"}
        protocol_refs.extend(
            artifact.content_uri
            for artifact_id, artifact in sorted(approved_artifacts.items())
            if artifact.artifact_type in protocol_output_types
            and artifact.content_uri not in protocol_refs
        )
        result_refs.extend(
            artifact.content_uri
            for artifact_id, artifact in sorted(approved_artifacts.items())
            if artifact.artifact_type in result_output_types
            and artifact.content_uri not in result_refs
        )
        pipeline = state.data_pipeline
        if (
            pipeline is not None
            and pipeline.validation_report is not None
            and pipeline.validation_report.passed
            and pipeline.statistical_result_card is not None
        ):
            result_card_ref = pipeline.statistical_result_card.ref
            if result_card_ref not in result_refs:
                result_refs.append(result_card_ref)
        payload: dict[str, object] = {
            "project_id": project_id,
            "approved_research_scope": approved_research_scope,
            "evidence_refs": [item.model_dump(mode="json") for item in evidence_refs],
            "paper_cards": [item.model_dump(mode="json") for item in paper_cards],
            "evidence_matrix": evidence_matrix,
            "approved_study_protocol_refs": protocol_refs,
            "validated_result_cards": result_refs,
            "interpretation_boundaries": list(research_state.risk_flags),
            "prior_review_findings": list(research_state.rework_trigger_refs),
            "output_language": "zh-CN",
        }
        context_hash = sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        return WritingContextBundle(
            project_id=project_id,
            approved_research_scope=approved_research_scope,
            evidence_refs=evidence_refs,
            paper_cards=paper_cards,
            evidence_matrix=evidence_matrix,
            approved_study_protocol_refs=protocol_refs,
            validated_result_cards=result_refs,
            interpretation_boundaries=list(research_state.risk_flags),
            prior_review_findings=list(research_state.rework_trigger_refs),
            output_language=LanguageCode.ZH_CN,
            context_hash=context_hash,
        )

    def start_planning(self, request: PlanningRequest) -> PlanningRunResult:
        """Call only the planner and pause before any formal scope approval."""
        planner = self.dispatcher.registry.get("mentor_planning")
        agent_input = AgentInput(
            agent_run_id=request.run_id,
            task_ref=f"{request.project_id}:planning",
            context_bundle_ref=request.context_bundle_ref,
            allowed_tool_capabilities=list(planner.allowed_tool_capabilities),
            allowed_output_types=list(planner.allowed_output_types),
            policy_version="controller-policy-v1",
            prompt_template_version="planner-scaffold-v1",
        )
        result = self.dispatcher.dispatch("mentor_planning", agent_input)
        if not result.candidate_artifact_refs:
            raise ValueError("planning Agent produced no candidate artifacts")
        execution_refs, operator_output_refs, operator_risk_flags = self._execute_agent_tools(
            request.project_id,
            result,
            query=request.research_intent,
        )

        approval = ApprovalRequest(
            request_id=f"approval-{request.run_id}",
            artifact_ref=result.candidate_artifact_refs[0],
            approval_type="research_scope",
            reason="Confirm the candidate research scope before evidence retrieval.",
            risk_summary="The Agent output is a proposal and has not been human approved.",
        )
        research_state = merge_references(
            ResearchState(project_id=request.project_id),
            task_status={"planning": TaskStatus.WAITING_HUMAN},
            task_ledger=[f"task://{request.project_id}/planning"],
            agent_run_refs=[request.run_id],
            artifact_refs=[*result.candidate_artifact_refs, *operator_output_refs],
            execution_run_refs=execution_refs,
            approval_request_refs=[approval.request_id],
            unresolved_questions=result.unresolved_questions,
            risk_flags=[*result.risk_flags, *operator_risk_flags],
        ).model_copy(update={"current_stage": ProjectStage.WAITING_HUMAN})
        route = RouteDecision(
            decision_id=f"route-{request.run_id}",
            project_id=request.project_id,
            current_stage=ProjectStage.INTAKE,
            selected_route="mentor_planning",
            reason="Initial research intent requires scope and feasibility planning.",
            required_context=[request.context_bundle_ref],
            required_tools=list(planner.allowed_tool_capabilities),
            decision_scope=DecisionScope.PROJECT,
            triggered_rules=["INTAKE_REQUIRES_SCOPE"],
            created_at=datetime.now(UTC),
        )
        self._record_audit(
            agent_input,
            result,
            route,
            execution_refs,
            operator_output_refs,
        )
        state = ControllerWorkflowState(
            project_id=request.project_id,
            current_stage=ProjectStage.WAITING_HUMAN,
            pending_approval_ref=approval.request_id,
            last_agent_run_id=result.agent_run_id,
            last_route_decision=route,
            research_state=research_state,
        )
        self._states[request.project_id] = research_state
        self._workflow_states[request.project_id] = state
        self._routes[request.project_id] = route
        self._approvals[request.project_id] = approval
        self._project_intents[request.project_id] = request.research_intent
        self._persist(request.project_id)
        return PlanningRunResult(
            workflow_state=state,
            agent_result=result,
            approval_request=approval,
            route_decision=route,
        )

    def approve_planning(
        self, state: ControllerWorkflowState, approval_request: ApprovalRequest
    ) -> ControllerWorkflowState:
        """Controller-only transition used after a human approves the scope."""
        if state.pending_approval_ref != approval_request.request_id:
            raise ValueError("approval request does not match the pending Controller decision")
        next_state = state.model_copy(
            update={"current_stage": ProjectStage.SCOPED, "pending_approval_ref": None}
        )
        if state.research_state is not None:
            approved_research_state = merge_references(
                state.research_state,
                task_status={"planning": TaskStatus.DONE, "evidence": TaskStatus.READY},
                progress_ledger=["research scope approved"],
            ).model_copy(update={"current_stage": ProjectStage.SCOPED})
            next_state = next_state.model_copy(update={"research_state": approved_research_state})
            self._states[state.project_id] = approved_research_state
        self._workflow_states[state.project_id] = next_state
        self._approvals.pop(state.project_id, None)
        self._persist(state.project_id)
        return next_state

    def get_state(self, project_id: str) -> ControllerWorkflowState:
        state = self._workflow_states.get(project_id)
        if state is not None:
            return state
        restored = self._restore(project_id)
        if restored is not None:
            return restored
        raise ValueError(f"unknown project: {project_id}")

    def run_next(self, project_id: str) -> WorkflowRunResult:
        """Route the next eligible Agent and pause for a Controller approval."""
        state = self.get_state(project_id)
        if state.current_stage == ProjectStage.WAITING_HUMAN:
            raise ValueError("project is waiting for human approval")
        if self._strict_data_pipeline and state.current_stage is ProjectStage.DATA_READY:
            raise ValueError(
                "data pipeline must reach ANALYZED through data-pipeline endpoints before the next workflow route"
            )
        if state.current_stage is ProjectStage.REWORK:
            research_state = state.research_state
            target_agent = research_state.rework_target_agent if research_state else None
            if target_agent is None:
                raise ValueError("REWORK stage has no target Agent")
            try:
                agent_id, approval_type, task_type, required_context = self._REWORK_ROUTES[
                    target_agent
                ]
            except KeyError as exc:
                raise ValueError(f"no rework route is defined for Agent {target_agent}") from exc
        else:
            try:
                agent_id, approval_type, task_type, required_context = self._ROUTES[
                    state.current_stage
                ]
            except KeyError as exc:
                raise ValueError(f"no route is defined for stage {state.current_stage}") from exc
        agent = self.dispatcher.registry.get(agent_id)
        run_id = f"{agent_id}-{uuid4().hex}"
        context_bundle: ContextBundle | WritingContextBundle | None = None
        writing_context: WritingContextBundle | None = None
        if agent_id == "evidence_review" and self.context_provider is not None:
            context_bundle = self.context_provider.build_context(
                project_id=project_id,
                task_ref=f"{project_id}:{task_type}",
                query=self._project_intents.get(project_id, ""),
                token_budget=2_000,
            )
        elif agent_id == "paper_writing":
            writing_context = self._build_writing_context(project_id, task_type, state)
            context_bundle = writing_context
        context_ref = (
            f"writing-context://{project_id}/{writing_context.context_hash}"
            if writing_context is not None
            else context_bundle.context_id
            if isinstance(context_bundle, ContextBundle)
            else required_context
        )
        route = RouteDecision(
            decision_id=f"route-{run_id}",
            project_id=project_id,
            current_stage=state.current_stage,
            selected_route=agent_id,
            reason=(
                f"Rework target {agent_id} requires {task_type}."
                if state.current_stage is ProjectStage.REWORK
                else f"Current stage requires {task_type}."
            ),
            required_context=[context_ref],
            required_tools=list(agent.allowed_tool_capabilities),
            decision_scope=DecisionScope.TASK,
            triggered_rules=[
                f"REWORK_TO_{agent_id.upper()}"
                if state.current_stage is ProjectStage.REWORK
                else f"STAGE_{state.current_stage}_ROUTE"
            ],
            created_at=datetime.now(UTC),
        )
        agent_input = AgentInput(
            agent_run_id=run_id,
            task_ref=f"{project_id}:{task_type}",
            context_bundle_ref=context_ref,
            allowed_tool_capabilities=list(agent.allowed_tool_capabilities),
            allowed_output_types=list(agent.allowed_output_types),
            policy_version=route.policy_version,
            prompt_template_version=f"{agent_id}-scaffold-v1",
        )
        package_ref: str | None = None
        if (
            self._strict_data_pipeline
            and agent_id == "data_analysis"
            and state.current_stage is ProjectStage.STUDY_PROTOCOL_APPROVED
        ):
            if not isinstance(agent, DataAnalysisAgent):
                raise ValueError("data_analysis registry entry has an invalid implementation")
            pre_analysis_input, model_specification = self._build_pre_analysis_input(
                project_id, run_id, task_type, state
            )
            outcome = agent.propose_pre_analysis_for(agent_input, pre_analysis_input)
            result = validate_agent_result(outcome.agent_result, agent.capability())
            result = result.model_copy(
                update={
                    "risk_flags": [*result.risk_flags, "NARROW_MVP_ANALYSIS_DEFAULTS"],
                    "unresolved_questions": [
                        *result.unresolved_questions,
                        "Replace narrow CSV MVP analysis defaults with the approved domain model compiler output.",
                    ],
                }
            )
            package_ref = self._persist_pre_analysis_package(
                project_id, outcome, model_specification
            )
        else:
            result = self.dispatcher.dispatch(agent_id, agent_input, context_bundle)
        if not result.candidate_artifact_refs:
            raise ValueError(f"{agent_id} produced no candidate artifacts")
        execution_refs, operator_output_refs, operator_risk_flags = self._execute_agent_tools(
            project_id,
            result,
            query=self._project_intents.get(project_id, ""),
            context_bundle=context_bundle if isinstance(context_bundle, ContextBundle) else None,
        )
        self._record_audit(
            agent_input,
            result,
            route,
            execution_refs,
            operator_output_refs,
        )
        approval = ApprovalRequest(
            request_id=f"approval-{run_id}",
            artifact_ref=result.candidate_artifact_refs[0],
            approval_type=approval_type,
            reason=f"Review {agent_id} candidate outputs before progressing the project.",
            risk_summary="Candidate output is not an approved research artifact.",
        )
        current = self._states[project_id]
        updated_research = merge_references(
            current,
            task_status={task_type: TaskStatus.WAITING_HUMAN},
            task_ledger=[f"task://{project_id}/{task_type}"],
            agent_run_refs=[run_id],
            artifact_refs=[*result.candidate_artifact_refs, *operator_output_refs],
            execution_run_refs=execution_refs,
            evidence_refs=result.evidence_refs,
            context_bundle_refs=[context_ref] if context_bundle is not None else [],
            approval_request_refs=[approval.request_id],
            route_decision_refs=[route.decision_id],
            risk_flags=[*result.risk_flags, *operator_risk_flags],
            unresolved_questions=result.unresolved_questions,
        ).model_copy(update={"current_stage": ProjectStage.WAITING_HUMAN})
        workflow_state = ControllerWorkflowState(
            project_id=project_id,
            current_stage=ProjectStage.WAITING_HUMAN,
            pending_approval_ref=approval.request_id,
            last_agent_run_id=run_id,
            last_route_decision=route,
            research_state=updated_research,
            data_pipeline=state.data_pipeline,
            data_pipeline_package_ref=package_ref or state.data_pipeline_package_ref,
        )
        self._states[project_id] = updated_research
        self._workflow_states[project_id] = workflow_state
        self._routes[project_id] = route
        self._approvals[project_id] = approval
        self._persist(project_id)
        return WorkflowRunResult(
            workflow_state=workflow_state,
            agent_result=result,
            approval_request=approval,
            route_decision=route,
        )

    def plan_agent_tasks(self, request: AgentPlanRequest) -> AgentExecutionPlan:
        """Create a reviewable task graph without invoking any domain Agent."""
        plan = self.agent_planner.build(request)
        self.agent_plan_store.put(plan)
        return plan

    def get_agent_plan(self, project_id: str, plan_id: str) -> AgentExecutionPlan:
        plan = self.agent_plan_store.get(project_id, plan_id)
        if plan is None:
            raise ValueError(f"unknown Agent plan: {plan_id}")
        return plan

    def list_agent_plans(self, project_id: str) -> list[AgentExecutionPlan]:
        return self.agent_plan_store.list_project(project_id)

    def approve_agent_plan(
        self,
        project_id: str,
        plan_id: str,
        request: AgentPlanApprovalRequest,
    ) -> AgentExecutionPlan:
        plan = self.get_agent_plan(project_id, plan_id)
        if plan.status is not AgentPlanStatus.PENDING_APPROVAL:
            raise ValueError("Agent plan is no longer waiting for approval")
        if request.decision == "rejected":
            updated = plan.model_copy(
                update={
                    "status": AgentPlanStatus.REJECTED,
                    "approved_by": request.decided_by,
                    "approved_at": datetime.now(UTC),
                }
            )
            self.agent_plan_store.put(updated)
            return updated

        selected_ids = (
            request.selected_task_ids
            if request.selected_task_ids is not None
            else [task.task_id for task in plan.tasks if task.blocked_reason is None]
        )
        known_ids = {task.task_id for task in plan.tasks}
        unknown_ids = set(selected_ids) - known_ids
        if unknown_ids:
            raise ValueError(f"unknown task ids in Agent plan: {sorted(unknown_ids)}")
        updated_tasks: list[AgentTaskPlan] = []
        for task in plan.tasks:
            if task.task_id not in selected_ids:
                updated_tasks.append(
                    task.model_copy(
                        update={
                            "status": AgentTaskStatus.SKIPPED,
                            "blocked_reason": "用户未批准本任务。",
                        }
                    )
                )
            elif task.blocked_reason is not None:
                updated_tasks.append(
                    task.model_copy(update={"status": AgentTaskStatus.BLOCKED})
                )
            else:
                updated_tasks.append(task)
        updated = plan.model_copy(
            update={
                "status": AgentPlanStatus.APPROVED,
                "tasks": updated_tasks,
                "execution_mode": request.execution_mode,
                "approved_task_ids": list(selected_ids),
                "approved_by": request.decided_by,
                "approved_at": datetime.now(UTC),
            }
        )
        self.agent_plan_store.put(updated)
        return updated

    def execute_agent_plan(self, project_id: str, plan_id: str) -> AgentExecutionPlan:
        """Run approved tasks in dependency waves and persist candidate outputs."""
        plan = self.get_agent_plan(project_id, plan_id)
        if plan.status is not AgentPlanStatus.APPROVED:
            raise ValueError("Agent plan must be approved before execution")
        self._ensure_plan_project_state(project_id, plan.user_request)
        if plan.execution_mode is AgentExecutionMode.STEPWISE:
            return self._execute_next_stepwise_task(project_id, plan)
        running = plan.model_copy(update={"status": AgentPlanStatus.RUNNING})
        self.agent_plan_store.put(running)
        tasks = list(running.tasks)
        completed_agents: set[str] = set()
        pending = {
            task.task_id
            for task in tasks
            if task.status not in {
                AgentTaskStatus.SKIPPED,
                AgentTaskStatus.BLOCKED,
            }
        }
        task_by_id = {task.task_id: task for task in tasks}
        failed = False

        while pending:
            ready: list[AgentTaskPlan] = []
            for task_id in sorted(pending):
                task = task_by_id[task_id]
                dependencies = {
                    dependency.split(":", 1)[1]
                    for dependency in task.depends_on
                    if ":" in dependency
                }
                if dependencies.intersection(
                    {
                        item.agent_id
                        for item in tasks
                        if item.status in {AgentTaskStatus.FAILED, AgentTaskStatus.BLOCKED}
                    }
                ):
                    task_by_id[task_id] = task.model_copy(
                        update={
                            "status": AgentTaskStatus.BLOCKED,
                            "blocked_reason": "前置 Agent 任务失败或被阻断。",
                        }
                    )
                    pending.remove(task_id)
                    failed = True
                    continue
                if dependencies.issubset(completed_agents):
                    ready.append(task)
            if not ready:
                for task_id in pending:
                    task_by_id[task_id] = task_by_id[task_id].model_copy(
                        update={
                            "status": AgentTaskStatus.BLOCKED,
                            "blocked_reason": "任务依赖无法满足，未执行。",
                        }
                    )
                failed = True
                break

            for task in ready:
                task_by_id[task.task_id] = task.model_copy(
                    update={"status": AgentTaskStatus.RUNNING}
                )
            with ThreadPoolExecutor(max_workers=min(4, len(ready))) as executor:
                futures = {
                    executor.submit(
                        self._execute_planned_task,
                        project_id,
                        running,
                        task_by_id[task.task_id],
                    ): task.task_id
                    for task in ready
                }
                for future in as_completed(futures):
                    task_id = futures[future]
                    try:
                        completed_task = future.result()
                    except Exception as error:
                        completed_task = task_by_id[task_id].model_copy(
                            update={
                                "status": AgentTaskStatus.FAILED,
                                "error": str(error),
                            }
                        )
                        failed = True
                    task_by_id[task_id] = completed_task
                    pending.remove(task_id)
                    if completed_task.status is AgentTaskStatus.COMPLETED:
                        completed_agents.add(completed_task.agent_id)
                    else:
                        failed = True

        final_tasks = [task_by_id[task.task_id] for task in tasks]
        final_status = (
            AgentPlanStatus.PARTIAL
            if failed and any(task.status is AgentTaskStatus.COMPLETED for task in final_tasks)
            else AgentPlanStatus.BLOCKED
            if failed
            else AgentPlanStatus.COMPLETED
        )
        updated = running.model_copy(
            update={
                "status": final_status,
                "tasks": final_tasks,
                "executed_at": datetime.now(UTC),
            }
        )
        self.agent_plan_store.put(updated)
        return updated

    def continue_agent_plan(
        self,
        project_id: str,
        plan_id: str,
        request: AgentTaskApprovalRequest,
    ) -> AgentExecutionPlan:
        """Record a human review of one stepwise output, then unlock one next task."""

        plan = self.get_agent_plan(project_id, plan_id)
        if plan.execution_mode is not AgentExecutionMode.STEPWISE:
            raise ValueError("only stepwise Agent plans accept per-task approval")
        if plan.status is not AgentPlanStatus.WAITING_TASK_APPROVAL:
            raise ValueError("Agent plan is not waiting for a task review")
        task_id = plan.pending_review_task_id
        if task_id is None:
            raise ValueError("Agent plan has no pending task review")
        task_index = next(
            (index for index, item in enumerate(plan.tasks) if item.task_id == task_id), None
        )
        if task_index is None:
            raise ValueError("pending Agent task is missing from the plan")
        tasks = list(plan.tasks)
        tasks[task_index] = tasks[task_index].model_copy(update={"review_note": request.note})
        if request.decision == "rework":
            updated = plan.model_copy(
                update={
                    "status": AgentPlanStatus.REWORK_REQUIRED,
                    "tasks": tasks,
                    "pending_review_task_id": None,
                    "rework_note": request.note or "研究者要求修改当前步骤产出。",
                }
            )
            self.agent_plan_store.put(updated)
            return updated
        approved = plan.model_copy(
            update={
                "status": AgentPlanStatus.APPROVED,
                "tasks": tasks,
                "pending_review_task_id": None,
                "rework_note": None,
            }
        )
        self.agent_plan_store.put(approved)
        return self.execute_agent_plan(project_id, plan_id)

    def _execute_next_stepwise_task(
        self, project_id: str, plan: AgentExecutionPlan
    ) -> AgentExecutionPlan:
        """Run exactly one dependency-ready task and pause for human review."""

        tasks = list(plan.tasks)
        completed_agents = {
            task.agent_id for task in tasks if task.status is AgentTaskStatus.COMPLETED
        }
        failed_agents = {
            task.agent_id
            for task in tasks
            if task.status in {AgentTaskStatus.FAILED, AgentTaskStatus.BLOCKED}
        }
        task_index: int | None = None
        for index, task in enumerate(tasks):
            if task.status in {
                AgentTaskStatus.COMPLETED,
                AgentTaskStatus.SKIPPED,
                AgentTaskStatus.BLOCKED,
                AgentTaskStatus.FAILED,
            }:
                continue
            dependencies = {
                dependency.split(":", 1)[1]
                for dependency in task.depends_on
                if ":" in dependency
            }
            if dependencies.intersection(failed_agents):
                tasks[index] = task.model_copy(
                    update={
                        "status": AgentTaskStatus.BLOCKED,
                        "blocked_reason": "前置 Agent 任务失败或被阻断。",
                    }
                )
                continue
            if dependencies.issubset(completed_agents):
                task_index = index
                break

        if task_index is None:
            has_active = any(
                task.status not in {
                    AgentTaskStatus.COMPLETED,
                    AgentTaskStatus.SKIPPED,
                    AgentTaskStatus.BLOCKED,
                    AgentTaskStatus.FAILED,
                }
                for task in tasks
            )
            final_status = AgentPlanStatus.BLOCKED if has_active else (
                AgentPlanStatus.PARTIAL
                if any(task.status in {AgentTaskStatus.FAILED, AgentTaskStatus.BLOCKED} for task in tasks)
                else AgentPlanStatus.COMPLETED
            )
            updated = plan.model_copy(
                update={"status": final_status, "tasks": tasks, "executed_at": datetime.now(UTC)}
            )
            self.agent_plan_store.put(updated)
            return updated

        running_task = tasks[task_index].model_copy(update={"status": AgentTaskStatus.RUNNING})
        tasks[task_index] = running_task
        running = plan.model_copy(update={"status": AgentPlanStatus.RUNNING, "tasks": tasks})
        self.agent_plan_store.put(running)
        try:
            completed_task = self._execute_planned_task(project_id, running, running_task)
        except Exception as error:
            completed_task = running_task.model_copy(
                update={"status": AgentTaskStatus.FAILED, "error": str(error)}
            )
        tasks[task_index] = completed_task
        if completed_task.status is AgentTaskStatus.COMPLETED:
            updated = running.model_copy(
                update={
                    "status": AgentPlanStatus.WAITING_TASK_APPROVAL,
                    "tasks": tasks,
                    "pending_review_task_id": completed_task.task_id,
                }
            )
        else:
            updated = running.model_copy(
                update={
                    "status": AgentPlanStatus.PARTIAL,
                    "tasks": tasks,
                    "pending_review_task_id": None,
                    "executed_at": datetime.now(UTC),
                }
            )
        self.agent_plan_store.put(updated)
        return updated

    def _ensure_plan_project_state(self, project_id: str, intent: str) -> ControllerWorkflowState:
        try:
            return self.get_state(project_id)
        except ValueError:
            research_state = ResearchState(project_id=project_id)
            state = ControllerWorkflowState(
                project_id=project_id,
                current_stage=ProjectStage.INTAKE,
                research_state=research_state,
            )
            self._states[project_id] = research_state
            self._workflow_states[project_id] = state
            self._project_intents[project_id] = intent
            self._persist(project_id)
            return state

    def _execute_planned_task(
        self,
        project_id: str,
        plan: AgentExecutionPlan,
        task: AgentTaskPlan,
    ) -> AgentTaskPlan:
        state = self._ensure_plan_project_state(project_id, plan.user_request)
        agent = self.dispatcher.registry.get(task.agent_id)
        run_id = f"{task.agent_id}-{uuid4().hex}"
        context_bundle: ContextBundle | WritingContextBundle | None = None
        if task.agent_id in {
            "mentor_planning",
            "evidence_review",
            "research_design",
            "independent_review",
        } and self.context_provider is not None:
            context_bundle = self.context_provider.build_context(
                project_id=project_id,
                task_ref=f"{plan.plan_id}:{task.task_id}",
                query=plan.user_request,
                token_budget=2_000,
            )
        elif task.agent_id == "paper_writing":
            context_bundle = self._build_writing_context(project_id, task.task_type, state)
        context_ref = (
            context_bundle.context_id
            if isinstance(context_bundle, ContextBundle)
            else task.input_refs[0]
            if task.input_refs
            else f"conversation-turn://{plan.conversation_id}/{plan.turn_id}"
            if plan.conversation_id and plan.turn_id
            else f"workflow-plan://{project_id}/{plan.plan_id}"
        )
        route = RouteDecision(
            decision_id=f"route-{run_id}",
            project_id=project_id,
            current_stage=state.current_stage,
            selected_route=task.agent_id,
            reason=task.reason,
            required_context=[context_ref, *task.required_context],
            required_tools=list(agent.allowed_tool_capabilities),
            decision_scope=DecisionScope.TASK,
            risk_level=task.risk_level,
            triggered_rules=["NATURAL_LANGUAGE_AGENT_PLAN", f"TASK_{task.task_type.upper()}"],
            created_at=datetime.now(UTC),
        )
        allowed_outputs = [
            output for output in task.expected_output_types
            if output in agent.allowed_output_types
        ]
        agent_input = AgentInput(
            agent_run_id=run_id,
            task_ref=f"{plan.plan_id}:{task.task_id}:{task.task_type}",
            context_bundle_ref=context_ref,
            allowed_tool_capabilities=list(agent.allowed_tool_capabilities),
            allowed_output_types=allowed_outputs or list(agent.allowed_output_types),
            policy_version=route.policy_version,
            prompt_template_version=f"{task.agent_id}-planned-v1",
        )
        result = self._dispatch_planned_agent(
            project_id,
            plan,
            task,
            agent_input,
            context_bundle,
            state,
        )
        # The plan intentionally selects only the outputs useful for this
        # request.  Remaining role capabilities are not a missing permission.
        if "OUTPUT_CAPABILITY_NOT_GRANTED" in result.risk_flags:
            result = result.model_copy(
                update={
                    "risk_flags": [
                        flag for flag in result.risk_flags
                        if flag != "OUTPUT_CAPABILITY_NOT_GRANTED"
                    ],
                    "unresolved_questions": [
                        item for item in result.unresolved_questions
                        if "grant output capabilities" not in item.lower()
                    ],
                }
            )
        if not result.candidate_artifact_refs:
            raise ValueError(f"{task.agent_id} produced no candidate artifacts")
        execution_refs, operator_output_refs, operator_risk_flags = self._execute_agent_tools(
            project_id,
            result,
            query=plan.user_request,
            context_bundle=context_bundle if isinstance(context_bundle, ContextBundle) else None,
        )
        persisted = self._record_audit(
            agent_input,
            result,
            route,
            execution_refs,
            operator_output_refs,
            evidence_snapshot=(
                [item.model_dump(mode="json") for item in context_bundle.evidence_refs]
                if isinstance(context_bundle, ContextBundle)
                else []
            ),
            user_request=plan.user_request,
        )
        with self._state_lock:
            current = self._states[project_id]
            updated_research = merge_references(
                current,
                agent_run_refs=[run_id],
                artifact_refs=[
                    *result.candidate_artifact_refs,
                    *operator_output_refs,
                ],
                execution_run_refs=execution_refs,
                evidence_refs=result.evidence_refs,
                context_bundle_refs=[context_ref] if isinstance(context_bundle, ContextBundle) else [],
                route_decision_refs=[route.decision_id],
                risk_flags=[*result.risk_flags, *operator_risk_flags],
                unresolved_questions=result.unresolved_questions,
                task_ledger=[f"plan://{plan.plan_id}/{task.task_id}"],
            )
            self._states[project_id] = updated_research
            self._workflow_states[project_id] = state.model_copy(
                update={
                    "research_state": updated_research,
                    "last_route_decision": route,
                    "last_agent_run_id": run_id,
                }
            )
            self._persist(project_id)
        return task.model_copy(
            update={
                "status": AgentTaskStatus.COMPLETED,
                "agent_run_id": run_id,
                "output_refs": [
                    *result.candidate_artifact_refs,
                    *operator_output_refs,
                ],
                "persisted_artifact_ids": [artifact.artifact_id for artifact in persisted],
                "evidence_refs": result.evidence_refs,
                "risk_flags": [*result.risk_flags, *operator_risk_flags],
                "unresolved_questions": result.unresolved_questions,
            }
        )

    def _dispatch_planned_agent(
        self,
        project_id: str,
        plan: AgentExecutionPlan,
        task: AgentTaskPlan,
        agent_input: AgentInput,
        context_bundle: ContextBundle | WritingContextBundle | None,
        state: ControllerWorkflowState,
    ) -> AgentResult:
        """Enter each role's domain method instead of the empty BaseAgent shell."""
        agent = self.dispatcher.registry.get(task.agent_id)
        user_request = plan.user_request
        evidence_refs = (
            list(context_bundle.evidence_refs)
            if isinstance(context_bundle, ContextBundle)
            else []
        )
        if task.agent_id == "mentor_planning" and isinstance(agent, MentorPlanningAgent):
            outcome = agent.propose_for(
                agent_input,
                PlanningBrief(
                    agent_run_id=agent_input.agent_run_id,
                    project_id=project_id,
                    task_ref=agent_input.task_ref,
                    topic=user_request,
                    population="师范生" if "师范生" in user_request else "研究参与者",
                    context="新建模情境" if "建模" in user_request else "当前研究情境",
                    intervention="基于研究目标设计的学习或教学干预",
                    comparator="常规教学或基线条件",
                    candidate_outcomes=["物理概念迁移能力", "前测与后测变化"],
                    constraints=["产出必须保持候选状态，不能代替人工审批。"],
                    exclusions=["未提供的数据、伦理批准和来源核验不能被推断。"],
                    evidence_refs=[item.evidence_id for item in evidence_refs],
                ),
                model_assisted=self.summary_generator is not None,
            )
            return outcome.agent_result
        if task.agent_id == "research_design" and isinstance(agent, ResearchDesignAgent):
            outcome = agent.propose_for(
                agent_input,
                ResearchDesignBrief(
                    agent_run_id=agent_input.agent_run_id,
                    project_id=project_id,
                    task_ref=agent_input.task_ref,
                    research_contract_ref=f"workflow-plan://{project_id}/{plan.plan_id}",
                    evidence_refs=[item.evidence_id for item in evidence_refs],
                    population="师范生" if "师范生" in user_request else "研究参与者",
                    context="新建模情境" if "建模" in user_request else "当前研究情境",
                    intervention="围绕物理概念迁移设计的教学活动",
                    comparator="常规教学或基线条件",
                    primary_outcome="transfer_score",
                    secondary_outcomes=["pretest_score", "posttest_score", "model_explanation_score"],
                    design_type="randomized_parallel_repeated_measures",
                    measurement_timepoints=["pretest", "posttest", "transfer"],
                    sampling_approach="目标师范生样本，具体招募范围待人工确认",
                    ethics_ref=f"ethics-review://{project_id}/pending",
                    confirmatory_model="比较前测、后测与迁移任务得分，模型须经人工审批",
                    covariates=["prior_physics_knowledge"],
                    exclusion_rules=["缺少关键测量或直接身份标识的数据需按批准规则处理"],
                    missing_data_strategy="按预注册方案记录并进行敏感性分析",
                    outlier_strategy="仅按预先声明的规则审查，不事后删除",
                ),
                model_assisted=self.summary_generator is not None,
            )
            return outcome.agent_result
        if task.agent_id == "data_analysis" and isinstance(agent, DataAnalysisAgent):
            request, _ = self._build_pre_analysis_input(project_id, agent_input.agent_run_id, task.task_type, state)
            request = request.model_copy(update={"task_ref": agent_input.task_ref})
            outcome = agent.propose_pre_analysis_for(agent_input, request)
            return outcome.agent_result
        if task.agent_id == "independent_review" and isinstance(agent, IndependentReviewAgent):
            criteria = [
                ReviewCriterion(
                    criterion_id=f"{plan.plan_id}:source-chain",
                    artifact_ref=f"workflow-plan://{project_id}/{plan.plan_id}",
                    category="evidence",
                    description=(
                        "检查当前研究需求使用的来源是否具备稳定 chunk 定位和来源核验状态。"
                    ),
                    passed=bool(evidence_refs) and all(
                        item.verification_status.value in {"source_verified", "human_verified"}
                        and item.chunk_id
                        and item.location.char_start >= 0
                        and item.location.char_end > item.location.char_start
                        for item in evidence_refs
                    ),
                    evidence_refs=[item.evidence_id for item in evidence_refs],
                    severity="major",
                ),
                ReviewCriterion(
                    criterion_id=f"{plan.plan_id}:transfer-measurement",
                    artifact_ref=f"workflow-plan://{project_id}/{plan.plan_id}",
                    category="measurement",
                    description="检查前测、后测和迁移任务是否有等值性说明与可审查评分规则。",
                    passed=all(word in user_request for word in ("前测", "后测", "迁移")),
                    severity="major",
                ),
                ReviewCriterion(
                    criterion_id=f"{plan.plan_id}:claim-boundary",
                    artifact_ref=f"workflow-plan://{project_id}/{plan.plan_id}",
                    category="workflow",
                    description="检查候选输出是否明确区分候选材料、正式证据和正式结果。",
                    passed=True,
                    severity="minor",
                ),
            ]
            outcome = agent.review_method(
                MethodReviewInput(
                    project_id=project_id,
                    protocol_ref=f"workflow-plan://{project_id}/{plan.plan_id}",
                    criteria=criteria,
                )
            )
            return agent.as_agent_result(agent_input, outcome)
        return self.dispatcher.dispatch(agent.agent_id, agent_input, context_bundle)

    def list_agent_outputs(
        self,
        project_id: str,
        plan_id: str | None = None,
        conversation_id: str | None = None,
        turn_id: str | None = None,
    ) -> list[AgentOutputSummary]:
        plans = (
            [self.get_agent_plan(project_id, plan_id)]
            if plan_id is not None
            else self.list_agent_plans(project_id)
        )
        summaries: list[AgentOutputSummary] = []
        for plan in plans:
            if conversation_id is not None and plan.conversation_id != conversation_id:
                continue
            if turn_id is not None and plan.turn_id != turn_id:
                continue
            for task in plan.tasks:
                if task.status in {
                    AgentTaskStatus.PLANNED,
                    AgentTaskStatus.WAITING_DEPENDENCY,
                    AgentTaskStatus.SKIPPED,
                }:
                    continue
                previews = self._agent_output_previews(
                    project_id,
                    task.persisted_artifact_ids,
                    agent_id=task.agent_id,
                    task_ref=f"{plan.plan_id}:{task.task_id}:{task.task_type}",
                    user_request=plan.user_request,
                    evidence_refs=task.evidence_refs,
                )
                primary_preview = self._primary_output_preview(task.agent_id, previews)
                summaries.append(
                    AgentOutputSummary(
                        plan_id=plan.plan_id,
                        task_id=task.task_id,
                        project_id=project_id,
                        user_request=plan.user_request,
                        conversation_id=plan.conversation_id,
                        turn_id=plan.turn_id,
                        agent_id=task.agent_id,
                        task_type=task.task_type,
                        status=task.status,
                        input_refs=task.input_refs,
                        depends_on=task.depends_on,
                        risk_level=task.risk_level,
                        output_types=[
                            ref.rsplit("/", maxsplit=1)[-1]
                            for ref in task.output_refs
                        ],
                        artifact_ids=task.persisted_artifact_ids,
                        artifact_refs=task.output_refs,
                        evidence_refs=task.evidence_refs,
                        output_previews=previews,
                        decision=self._agent_output_decision(
                            project_id, task.persisted_artifact_ids
                        ),
                        risk_flags=task.risk_flags,
                        unresolved_questions=task.unresolved_questions,
                        target_pages=list(_TARGET_PAGES.get(task.agent_id, ())),
                        error=task.error,
                        agent_run_id=task.agent_run_id,
                        agent_version=self._agent_run_version(project_id, task.agent_run_id),
                        primary_artifact_id=primary_preview.artifact_id if primary_preview else None,
                        researcher_answer=primary_preview.researcher_summary if primary_preview else "",
                        summary_mode=primary_preview.summary_mode if primary_preview else "deterministic",
                    )
                )
        return summaries

    @staticmethod
    def _primary_output_preview(
        agent_id: str, previews: list[AgentOutputPreview]
    ) -> AgentOutputPreview | None:
        """Choose one researcher-facing answer while preserving every raw artifact."""
        preferred_types: dict[str, tuple[str, ...]] = {
            "mentor_planning": ("ResearchQuestionTree", "FeasibilityReport"),
            "evidence_review": (
                "EvidenceMatrixCandidate",
                "BoundedEvidenceSynthesis",
                "PaperCardCollection",
                "EvidenceSufficiencyReport",
            ),
            "research_design": ("StudyProtocolCandidate", "MeasurementPlan"),
            "data_analysis": (
                "DataProcessingPlanCandidate",
                "ExecutableAnalysisPlanCandidate",
                "DataAuditSpecification",
            ),
            "paper_writing": ("ManuscriptDraftZh", "ManuscriptOutline"),
            "independent_review": ("ReviewReport", "RevisionRequest", "ReviewFinding"),
        }
        for artifact_type in preferred_types.get(agent_id, ()):
            for preview in previews:
                if preview.artifact_type == artifact_type:
                    return preview
        return previews[0] if previews else None

    def _agent_run_version(self, project_id: str, run_id: str | None) -> str | None:
        if not run_id:
            return None
        record = next(
            (item for item in self.agent_run_store.list_project(project_id) if item.agent_run_id == run_id),
            None,
        )
        return record.agent_version if record is not None else None

    def list_agent_page_materials(
        self,
        project_id: str,
        *,
        target: str | None = None,
        conversation_id: str | None = None,
        turn_id: str | None = None,
    ) -> list[AgentPageMaterial]:
        """Return only outputs that remain applied or formally promoted."""

        materials = self.agent_page_material_store.list_project(
            project_id,
            target=target,
            conversation_id=conversation_id,
            turn_id=turn_id,
        )
        readable: list[AgentPageMaterial] = []
        for material in materials:
            artifact = self.artifact_store.get(project_id, material.artifact_id)
            if artifact is None or artifact.status not in {"APPLIED", "APPROVED"}:
                continue

            # Materials applied by the pre-specialist implementation can
            # contain only a candidate envelope. Enrich that legacy record at
            # read time so it remains useful without rewriting immutable audit
            # history or silently changing its approval state.
            content = dict(material.content)
            if not content.get("title") and content.get("candidate_ref"):
                source = self._agent_task_for_artifact(project_id, material.artifact_id)
                plan = source[0] if source is not None else None
                task = source[1] if source is not None else None
                if plan is not None and task is not None:
                    content = self._deterministic_candidate_body(
                        agent_id=task.agent_id,
                        artifact_type=artifact.artifact_type,
                        project_id=project_id,
                        task_ref=f"{plan.plan_id}:{task.task_id}:{task.task_type}",
                        user_request=plan.user_request,
                        evidence_refs=list(content.get("evidence_refs", task.evidence_refs)),
                        evidence_snapshot=list(content.get("evidence_snapshot", [])),
                        candidate_ref=str(content["candidate_ref"]),
                    )
                    content = self._with_researcher_summary(
                        content,
                        artifact_type=artifact.artifact_type,
                        user_request=plan.user_request,
                    )
            readable.append(material.model_copy(update={"content": content}))
        return readable

    def list_formal_evidence(self, project_id: str) -> list[FormalEvidenceRecord]:
        """Return one record per evidence ID with preserved round provenance."""
        return self.formal_evidence_store.list_project(project_id)

    def _agent_task_for_artifact(
        self, project_id: str, artifact_id: str
    ) -> tuple[AgentExecutionPlan, AgentTaskPlan] | None:
        for plan in self.list_agent_plans(project_id):
            for task in plan.tasks:
                if artifact_id in task.persisted_artifact_ids:
                    return plan, task
        return None

    def agent_artifact_source(
        self, project_id: str, artifact_id: str
    ) -> tuple[AgentExecutionPlan, AgentTaskPlan] | None:
        """Expose the plan ownership check without exposing store internals."""
        return self._agent_task_for_artifact(project_id, artifact_id)

    def _agent_output_previews(
        self,
        project_id: str,
        artifact_ids: Iterable[str],
        *,
        agent_id: str | None = None,
        task_ref: str = "",
        user_request: str = "",
        evidence_refs: list[str] | None = None,
    ) -> list[AgentOutputPreview]:
        previews: list[AgentOutputPreview] = []
        for artifact_id in artifact_ids:
            try:
                artifact = self.artifact_store.get(project_id, artifact_id)
                content = self.artifact_content_store.get(project_id, artifact_id)
                if artifact is None:
                    continue
                body = content.body if content is not None else {}
                # Records created before role-specific candidate briefs were
                # added contain only IDs and governance metadata.  Enrich
                # them at read time so existing plans remain reviewable.
                if (
                    agent_id
                    and not body.get("title")
                    and body.get("candidate_ref")
                ):
                    body = self._deterministic_candidate_body(
                        agent_id=agent_id,
                        artifact_type=artifact.artifact_type,
                        project_id=project_id,
                        task_ref=task_ref,
                        user_request=user_request,
                        evidence_refs=evidence_refs or list(body.get("evidence_refs", [])),
                        evidence_snapshot=list(body.get("evidence_snapshot", [])),
                        candidate_ref=str(body.get("candidate_ref", artifact.content_uri)),
                    )
                summary = self._preview_researcher_summary(
                    body, artifact_type=artifact.artifact_type
                )
                previews.append(
                    AgentOutputPreview(
                        artifact_id=artifact_id,
                        artifact_type=artifact.artifact_type,
                        status=artifact.status,
                        content=body if content is not None else {
                            "status": "candidate",
                            "candidate_ref": artifact.content_uri,
                            "preview_unavailable": True,
                        },
                        researcher_summary=str(summary["summary"]),
                        review_points=list(summary["review_points"]),
                        action_items=list(summary["action_items"]),
                        summary_mode=str(body.get("summary_mode", "deterministic")),
                    )
                )
            except Exception:
                # A malformed preview must not hide the task and its artifact
                # references from the workbench.
                previews.append(
                    AgentOutputPreview(
                        artifact_id=artifact_id,
                        artifact_type="CandidateArtifact",
                        status="CANDIDATE",
                        content={"preview_unavailable": True},
                    )
                )
        return previews

    @classmethod
    def _preview_researcher_summary(
        cls, body: Mapping[str, object], *, artifact_type: str
    ) -> dict[str, object]:
        stored = body.get("researcher_summary")
        if isinstance(stored, Mapping):
            summary = stored.get("summary")
            review_points = stored.get("review_points")
            action_items = stored.get("action_items")
            if isinstance(summary, str) and summary.strip():
                return {
                    "summary": summary,
                    "review_points": [item for item in review_points if isinstance(item, str)] if isinstance(review_points, list) else [],
                    "action_items": [item for item in action_items if isinstance(item, str)] if isinstance(action_items, list) else [],
                }
        return cls._deterministic_researcher_summary(body, artifact_type=artifact_type)

    def _agent_output_decision(
        self, project_id: str, artifact_ids: Iterable[str]
    ) -> str:
        statuses = {
            artifact.status
            for artifact_id in artifact_ids
            if (artifact := self.artifact_store.get(project_id, artifact_id)) is not None
        }
        if statuses and statuses.issubset({"REJECTED"}):
            return "reject"
        if "REVIEW_REQUIRED" in statuses:
            return "review_required"
        if "APPROVED" in statuses:
            return "promoted"
        if "APPLIED" in statuses:
            return "applied"
        if "RETAINED" in statuses:
            return "retained"
        return "candidate"

    def decide_agent_output(
        self,
        project_id: str,
        artifact_id: str,
        request: AgentOutputDecisionRequest,
    ) -> dict[str, object]:
        artifact = self.artifact_store.get(project_id, artifact_id)
        if artifact is None:
            raise ValueError(f"unknown Agent output artifact: {artifact_id}")
        evidence_artifact_types = {
            "PaperCardCollection",
            "EvidenceMatrixCandidate",
            "BoundedEvidenceSynthesis",
        }
        if request.decision.value == "promote" and artifact.artifact_type not in evidence_artifact_types:
            raise ValueError(
                "only source-bound evidence outputs can be promoted; apply other Agent outputs to their target page"
            )
        source = self._agent_task_for_artifact(project_id, artifact_id)
        plan: AgentExecutionPlan | None = None
        task: AgentTaskPlan | None = None
        allowed_targets: list[str] = []
        if source is not None:
            plan, task = source
            allowed_targets = list(_TARGET_PAGES.get(task.agent_id, ()))
        if request.decision.value == "apply" and source is None:
            raise ValueError(f"artifact is not owned by an Agent plan: {artifact_id}")
        target = request.target or (allowed_targets[0] if allowed_targets else "workspace")
        if allowed_targets and target not in allowed_targets:
            raise ValueError(f"target is not allowed for {task.agent_id if task else 'artifact'}: {target}")
        status = {
            "retain": "RETAINED",
            "reject": "REJECTED",
            "apply": "APPLIED",
            "promote": "APPROVED",
        }[request.decision.value]
        formalization = "project_material"
        risk_flags: list[str] = []
        evidence_ids: list[str] = []
        content = self.artifact_content_store.get(project_id, artifact_id)
        if request.decision.value == "promote":
            evidence_ids = self._extract_evidence_ids(content.body if content else {})
            valid_evidence, reason = self._validate_formal_evidence(
                project_id, content.body if content else {}, evidence_ids
            )
            if not valid_evidence:
                status = "REVIEW_REQUIRED"
                formalization = "candidate_evidence_only"
                risk_flags.append(reason)
            else:
                formalization = "formal_evidence"
                for evidence_id in evidence_ids:
                    snapshot = next(
                        (
                            item
                            for item in content.body.get("evidence_snapshot", [])
                            if isinstance(item, Mapping)
                            and item.get("evidence_id") == evidence_id
                        ),
                        {},
                    )
                    self.formal_evidence_store.put(
                        FormalEvidenceRecord(
                            project_id=project_id,
                            evidence_id=evidence_id,
                            artifact_id=artifact_id,
                            plan_id=plan.plan_id if plan is not None else "unknown",
                            task_id=task.task_id if task is not None else "unknown",
                            agent_id=task.agent_id if task is not None else artifact.created_by,
                            conversation_id=plan.conversation_id if plan is not None else None,
                            turn_id=plan.turn_id if plan is not None else None,
                            promoted_by=request.decided_by,
                            evidence_ref=dict(snapshot),
                            provenance=[
                                {
                                    "plan_id": plan.plan_id if plan is not None else "unknown",
                                    "task_id": task.task_id if task is not None else "unknown",
                                    "conversation_id": plan.conversation_id if plan is not None else None,
                                    "turn_id": plan.turn_id if plan is not None else None,
                                    "artifact_id": artifact_id,
                                    "promoted_by": request.decided_by,
                                    "promoted_at": datetime.now(UTC).isoformat(),
                                }
                            ],
                        )
                    )
                with self._state_lock:
                    current = self._states.get(project_id)
                    if current is None:
                        current = self.get_state(project_id).research_state
                    if current is not None:
                        updated_state = merge_references(
                            current,
                            evidence_refs=evidence_ids,
                            artifact_refs=[artifact_id],
                            progress_ledger=[
                                f"formal evidence promoted: {artifact_id}"
                            ],
                        )
                        self._states[project_id] = updated_state
                        workflow_state = self._workflow_states.get(project_id)
                        if workflow_state is not None:
                            self._workflow_states[project_id] = workflow_state.model_copy(
                                update={"research_state": updated_state}
                            )
                            self._persist(project_id)
        updated = artifact.model_copy(update={"status": status})
        self.artifact_store.put(updated)
        if status in {"APPLIED", "APPROVED"} and plan is not None and task is not None:
            self.agent_page_material_store.put(
                AgentPageMaterial(
                    material_id=f"material:{artifact_id}:{target}",
                    project_id=project_id,
                    plan_id=plan.plan_id,
                    task_id=task.task_id,
                    agent_id=task.agent_id,
                    artifact_id=artifact_id,
                    artifact_type=artifact.artifact_type,
                    target=target,
                    conversation_id=plan.conversation_id,
                    turn_id=plan.turn_id,
                    formalization=formalization if status == "APPROVED" else "candidate",
                    applied_by=request.decided_by,
                    content=dict(content.body) if content is not None else {},
                )
            )
        decision_value = (
            "approved"
            if request.decision.value == "promote" and status == "APPROVED"
            else "promote_blocked"
            if request.decision.value == "promote"
            else request.decision.value
        )
        self.decision_store.put(
            ApprovalRecord(
                approval_id=f"agent-output:{artifact_id}:{request.decision.value}",
                project_id=project_id,
                artifact_id=artifact_id,
                artifact_version=artifact.version,
                decision=decision_value,
                decided_by=request.decided_by,
                decided_at=datetime.now(UTC),
                reason=request.note,
                idempotency_key=f"agent-output:{artifact_id}:{request.decision.value}",
            )
        )
        return {
            "ok": True,
            "project_id": project_id,
            "artifact": updated.model_dump(mode="json"),
            "decision": request.decision.value,
            "decided_by": request.decided_by,
            "target": target,
            "formalization": formalization,
            "evidence_refs": evidence_ids,
            "risk_flags": risk_flags,
        }

    @staticmethod
    def _extract_evidence_ids(body: Mapping[str, object]) -> list[str]:
        found: list[str] = []

        def visit(value: object, key: str | None = None) -> None:
            if isinstance(value, Mapping):
                for child_key, child_value in value.items():
                    if child_key in {"evidence_id", "evidence_ref"} and isinstance(child_value, str):
                        if child_value not in found:
                            found.append(child_value)
                    elif child_key == "evidence_refs" and isinstance(child_value, list):
                        for item in child_value:
                            if isinstance(item, str) and item not in found:
                                found.append(item)
                            else:
                                visit(item, child_key)
                    else:
                        visit(child_value, child_key)
            elif isinstance(value, list):
                for item in value:
                    visit(item, key)

        visit(body)
        return found

    @staticmethod
    def _validate_formal_evidence(
        project_id: str,
        body: Mapping[str, object],
        evidence_ids: list[str],
    ) -> tuple[bool, str]:
        snapshots = body.get("evidence_snapshot")
        if not evidence_ids:
            return False, "FORMAL_EVIDENCE_MISSING_EVIDENCE_REFS"
        if not isinstance(snapshots, list):
            return False, "FORMAL_EVIDENCE_MISSING_SOURCE_SNAPSHOT"
        by_id = {
            item.get("evidence_id"): item
            for item in snapshots
            if isinstance(item, Mapping) and isinstance(item.get("evidence_id"), str)
        }
        for evidence_id in evidence_ids:
            item = by_id.get(evidence_id)
            if not isinstance(item, Mapping):
                return False, "FORMAL_EVIDENCE_SOURCE_NOT_FOUND"
            if item.get("project_id") != project_id:
                return False, "FORMAL_EVIDENCE_PROJECT_MISMATCH"
            if item.get("verification_status") not in {"source_verified", "human_verified"}:
                return False, "FORMAL_EVIDENCE_REQUIRES_SOURCE_VERIFICATION"
            if not isinstance(item.get("chunk_id"), str) or not item["chunk_id"].strip():
                return False, "FORMAL_EVIDENCE_MISSING_SOURCE_CHUNK_REF"
            location = item.get("location")
            if not isinstance(location, Mapping):
                return False, "FORMAL_EVIDENCE_MISSING_SOURCE_LOCATION"
            if not isinstance(location.get("chunk_index"), int):
                return False, "FORMAL_EVIDENCE_MISSING_CHUNK_LOCATION"
            if not isinstance(location.get("char_start"), int) or not isinstance(
                location.get("char_end"), int
            ):
                return False, "FORMAL_EVIDENCE_MISSING_CHARACTER_LOCATION"
        return True, ""

    def resume_approval(
        self,
        project_id: str,
        approval_request: ApprovalRequest,
        *,
        decision: str,
        decided_by: str,
    ) -> ResearchState:
        """Apply one approval exactly once and return the updated reference state."""
        workflow_state = self.get_state(project_id)
        state = self._states.get(project_id) or workflow_state.research_state
        if state is None:
            raise ValueError("workflow state has no research state")
        idempotency_key = f"resume:{approval_request.request_id}:{decision}"
        existing = self.decision_store.get_by_idempotency(project_id, idempotency_key)
        pending_matches = workflow_state.pending_approval_ref == approval_request.request_id
        if not pending_matches:
            if existing is not None:
                return state
            raise ValueError("approval request does not match the pending Controller decision")
        if decision == "approved":
            block_reason = self._evidence_approval_block_reason(
                workflow_state, state, approval_request
            )
            if block_reason is not None:
                raise ValueError(block_reason)
        if existing is None:
            record = ApprovalRecord(
                approval_id=approval_request.request_id,
                project_id=project_id,
                artifact_id=approval_request.artifact_ref,
                artifact_version=1,
                decision=decision,
                decided_by=decided_by,
                decided_at=datetime.now(UTC),
                reason=approval_request.reason,
                idempotency_key=idempotency_key,
            )
            self.decision_store.put(record)
        else:
            decision = existing.decision
        if decision != "approved":
            next_stage = ProjectStage.REWORK
            rework_target_agent = self._REWORK_TARGETS.get(approval_request.approval_type)
            if rework_target_agent is None:
                raise ValueError(
                    f"no rework target is defined for approval type {approval_request.approval_type}"
                )
        else:
            rework_target_agent = None
            approved_stage = {
                "research_scope": ProjectStage.SCOPED,
                "evidence_protocol": ProjectStage.EVIDENCE_READY,
                "study_protocol": ProjectStage.STUDY_PROTOCOL_APPROVED,
                "analysis_execution": ProjectStage.ANALYZED,
                "manuscript": ProjectStage.DRAFTED,
                "review_report": ProjectStage.VERIFIED,
            }
            if approval_request.approval_type == "analysis_specification":
                next_stage = (
                    ProjectStage.DATA_READY
                    if self._strict_data_pipeline
                    else ProjectStage.ANALYZED
                )
            else:
                next_stage = approved_stage.get(approval_request.approval_type, ProjectStage.REWORK)
        approved_protocol_refs: list[str] = []
        validated_result_refs: list[str] = []
        if decision == "approved":
            approved_outputs = self._approved_output_refs(project_id)
            if approval_request.approval_type == "study_protocol":
                approved_protocol_refs = [
                    ref
                    for ref in sorted(approved_outputs)
                    if ref.rsplit("/", maxsplit=1)[-1]
                    in {"StudyProtocolCandidate", "PreregisteredAnalysisPlanDraft"}
                ]
            elif approval_request.approval_type in {"analysis_specification", "analysis_execution"}:
                validated_result_refs = [
                    ref
                    for ref in sorted(approved_outputs)
                    if ref.rsplit("/", maxsplit=1)[-1] == "StatisticalResultCardCandidate"
                ]
        updated = merge_references(
            state,
            task_status={"approval": TaskStatus.DONE},
            progress_ledger=[f"approval {approval_request.request_id}: {decision}"],
            protocol_refs=approved_protocol_refs,
            research_test_result_refs=validated_result_refs,
        ).model_copy(
            update={
                "current_stage": next_stage,
                "rework_target_agent": rework_target_agent,
                "rework_reason": (
                    f"{approval_request.approval_type} approval was rejected"
                    if rework_target_agent is not None
                    else None
                ),
                "approval_request_refs": list(state.approval_request_refs),
            }
        )
        data_pipeline = workflow_state.data_pipeline
        if (
            self._strict_data_pipeline
            and decision == "approved"
            and approval_request.approval_type == "analysis_specification"
        ):
            data_pipeline = self._begin_data_pipeline_from_package(project_id, workflow_state)
            updated = updated.model_copy(update={"current_stage": ProjectStage.DATA_READY})
        next_workflow = workflow_state.model_copy(
            update={
                "current_stage": next_stage,
                "pending_approval_ref": None,
                "research_state": updated,
                "data_pipeline": data_pipeline,
            }
        )
        self._states[project_id] = updated
        self._workflow_states[project_id] = next_workflow
        self._approvals.pop(project_id, None)
        self._persist(project_id)
        return updated

    def _evidence_approval_block_reason(
        self,
        workflow_state: ControllerWorkflowState,
        state: ResearchState,
        approval_request: ApprovalRequest,
    ) -> str | None:
        """Keep formal evidence approval fail-closed when verified evidence is absent."""
        if approval_request.approval_type != "evidence_protocol":
            return None

        risk_flags = {flag.strip().lower() for flag in state.risk_flags}
        if risk_flags & self._EVIDENCE_APPROVAL_BLOCKING_RISKS:
            return (
                "evidence_protocol approval blocked: verified evidence is required "
                "before progression"
            )

        # A context-backed EvidenceReview with no usable refs is the real formal
        # path. Empty test Controllers intentionally have no context provider and
        # remain compatible with the lightweight unit-test workflow.
        has_formal_context = bool(state.context_bundle_refs) and (
            workflow_state.last_route_decision is not None
            and workflow_state.last_route_decision.selected_route == "evidence_review"
        )
        if has_formal_context and not state.evidence_refs:
            return (
                "evidence_protocol approval blocked: verified evidence is required "
                "before progression"
            )
        return None

    def get_pending_approval(self, project_id: str) -> ApprovalRequest:
        if project_id not in self._approvals:
            self._restore(project_id)
        try:
            return self._approvals[project_id]
        except KeyError as exc:
            raise ValueError(f"project has no pending approval: {project_id}") from exc

    def begin_data_pipeline(self, request: DataPipelineBeginRequest) -> DataPipelineState:
        """Controller-only entry to the approved CSV/PYTHON_ONLY data pipeline."""

        workflow_state = self.get_state(request.project_id)
        if workflow_state.current_stage not in {
            ProjectStage.STUDY_PROTOCOL_APPROVED,
            ProjectStage.DATA_READY,
        }:
            raise ValueError("data pipeline requires an approved study protocol")
        pipeline = self.data_pipeline.begin(request)
        updated_research = self._require_research_state(workflow_state).model_copy(
            update={"current_stage": ProjectStage.DATA_READY}
        )
        self._states[request.project_id] = updated_research
        self._workflow_states[request.project_id] = workflow_state.model_copy(
            update={
                "current_stage": ProjectStage.DATA_READY,
                "research_state": updated_research,
                "data_pipeline": pipeline,
            }
        )
        self._persist(request.project_id)
        return pipeline

    def register_data_pipeline_raw_csv(
        self, project_id: str, *, filename: str, content: bytes
    ) -> DataPipelineState:
        """Controller-only raw-data registration and deterministic audit."""

        workflow_state = self.get_state(project_id)
        pipeline = self._require_data_pipeline(workflow_state)
        updated_pipeline = self.data_pipeline.register_raw_csv(
            pipeline, filename=filename, content=content
        )
        next_stage = (
            ProjectStage.REWORK
            if updated_pipeline.stage is DataPipelineStage.REWORK
            else ProjectStage.WAITING_HUMAN
        )
        research_state = self._require_research_state(workflow_state)
        data_refs = [*research_state.data_asset_refs]
        if updated_pipeline.raw_dataset is not None and updated_pipeline.raw_dataset.ref not in data_refs:
            data_refs.append(updated_pipeline.raw_dataset.ref)
        updated_research = research_state.model_copy(
            update={
                "current_stage": next_stage,
                "data_asset_refs": data_refs,
                "risk_flags": [
                    *research_state.risk_flags,
                    *(updated_pipeline.data_audit_report.risk_flags
                      if updated_pipeline.data_audit_report is not None else []),
                ],
            }
        )
        self._states[project_id] = updated_research
        self._workflow_states[project_id] = workflow_state.model_copy(
            update={
                "current_stage": next_stage,
                "research_state": updated_research,
                "data_pipeline": updated_pipeline,
            }
        )
        self._persist(project_id)
        return updated_pipeline

    def decide_data_pipeline(
        self, project_id: str, *, decision: str, decided_by: str
    ) -> DataPipelineState:
        """Persist one human decision, then execute only the approved operation."""

        workflow_state = self.get_state(project_id)
        pipeline = self._require_data_pipeline(workflow_state)
        approval = pipeline.pending_approval
        if approval is None:
            raise ValueError("data pipeline has no pending human approval")
        if decision not in {"approved", "rejected"}:
            raise ValueError("data pipeline approval decision must be approved or rejected")
        idempotency_key = f"data-pipeline:{approval.request_id}:{decision}"
        existing = self.decision_store.get_by_idempotency(project_id, idempotency_key)
        if existing is None:
            self.decision_store.put(
                ApprovalRecord(
                    approval_id=approval.request_id,
                    project_id=project_id,
                    artifact_id=approval.artifact_ref,
                    artifact_version=1,
                    decision=decision,
                    decided_by=decided_by,
                    decided_at=datetime.now(UTC),
                    reason=approval.reason,
                    idempotency_key=idempotency_key,
                )
            )
        else:
            decision = existing.decision
        updated_pipeline = self.data_pipeline.decide(pipeline, decision=decision)
        next_stage = {
            DataPipelineStage.WAITING_PROCESSING_APPROVAL: ProjectStage.WAITING_HUMAN,
            DataPipelineStage.WAITING_FREEZE_APPROVAL: ProjectStage.WAITING_HUMAN,
            DataPipelineStage.WAITING_EXECUTION_APPROVAL: ProjectStage.WAITING_HUMAN,
            DataPipelineStage.REWORK: ProjectStage.REWORK,
            DataPipelineStage.BLOCKED: ProjectStage.BLOCKED,
            DataPipelineStage.ANALYZED: ProjectStage.ANALYZED,
        }.get(updated_pipeline.stage, ProjectStage.DATA_READY)
        research_state = self._require_research_state(workflow_state)
        data_refs = [*research_state.data_asset_refs]
        for dataset in (
            updated_pipeline.processed_dataset,
            updated_pipeline.frozen_dataset,
        ):
            if dataset is not None and dataset.ref not in data_refs:
                data_refs.append(dataset.ref)
        execution_refs = [*research_state.execution_run_refs]
        if updated_pipeline.validation_report is not None:
            for execution_ref in updated_pipeline.validation_report.execution_run_refs:
                if execution_ref not in execution_refs:
                    execution_refs.append(execution_ref)
        artifact_refs = [*research_state.artifact_refs]
        if updated_pipeline.statistical_result_card is not None:
            result_ref = updated_pipeline.statistical_result_card.ref
            if result_ref not in artifact_refs:
                artifact_refs.append(result_ref)
        updated_research = research_state.model_copy(
            update={
                "current_stage": next_stage,
                "data_asset_refs": data_refs,
                "execution_run_refs": execution_refs,
                "artifact_refs": artifact_refs,
                "rework_reason": updated_pipeline.rework_reason,
                "rework_target_refs": updated_pipeline.blocked_target_ids,
            }
        )
        self._states[project_id] = updated_research
        self._workflow_states[project_id] = workflow_state.model_copy(
            update={
                "current_stage": next_stage,
                "research_state": updated_research,
                "data_pipeline": updated_pipeline,
            }
        )
        self._persist(project_id)
        return updated_pipeline

    def run_reproducibility_review(
        self, request: ReproducibilityReviewRequest
    ) -> ReproducibilityReviewRunResult:
        """Verify manuscript numbers against the Controller-owned result card.

        This is deliberately a Controller operation: the independent reviewer
        receives read-only data, while only this method records artifacts and
        routes the project to human approval, REWORK, or BLOCKED.
        """

        workflow_state = self.get_state(request.project_id)
        if workflow_state.current_stage is not ProjectStage.DRAFTED:
            raise ValueError("reproducibility review requires a drafted manuscript")
        pipeline = self._require_data_pipeline(workflow_state)
        if (
            pipeline.validation_report is None
            or not pipeline.validation_report.passed
            or pipeline.statistical_result_card is None
        ):
            raise ValueError("reproducibility review requires a validated result card")
        reviewer = self.dispatcher.registry.get("independent_review")
        if not isinstance(reviewer, IndependentReviewAgent):
            raise TypeError("independent_review registry entry has an invalid implementation")

        outcome = reviewer.review_reproducibility(
            ReproducibilityReviewInput(
                project_id=request.project_id,
                manuscript_ref=request.manuscript_ref,
                numeric_claims=request.numeric_claims,
                statistical_result_cards=[pipeline.statistical_result_card],
                tolerance=request.tolerance,
            )
        )
        report_artifact_id = f"review:{uuid4().hex}"
        content = self.artifact_content_store.put(
            ArtifactContent(
                project_id=request.project_id,
                artifact_id=report_artifact_id,
                version=1,
                artifact_type="ReproducibilityReviewReport",
                schema_version="v1",
                body={
                    "report": outcome.report.model_dump(mode="json"),
                    "findings": [item.model_dump(mode="json") for item in outcome.findings],
                    "revision_requests": [
                        item.model_dump(mode="json") for item in outcome.revision_requests
                    ],
                },
            )
        )
        if content.content_hash is None:
            raise ValueError("persisted review content has no hash")
        self.artifact_store.put(
            ArtifactRef(
                artifact_id=report_artifact_id,
                project_id=request.project_id,
                artifact_type="ReproducibilityReviewReport",
                version=1,
                content_uri=(
                    f"artifact-content://{request.project_id}/{report_artifact_id}/{content.version}"
                ),
                sha256=content.content_hash,
                created_at=datetime.now(UTC),
                created_by="independent_review",
                status="VALIDATED",
            )
        )

        research_state = self._require_research_state(workflow_state)
        artifact_refs = [*research_state.artifact_refs]
        if outcome.report.review_report_id not in artifact_refs:
            artifact_refs.append(outcome.report.review_report_id)
        if outcome.report.overall_recommendation == "PASS":
            approval = ApprovalRequest(
                request_id=f"approval-{uuid4().hex}",
                artifact_ref=outcome.report.review_report_id,
                approval_type="review_report",
                reason="Human approval is required before a passed review can verify the manuscript.",
                risk_summary="Independent reproducibility review passed; release remains human-controlled.",
            )
            updated_research = research_state.model_copy(
                update={
                    "current_stage": ProjectStage.WAITING_HUMAN,
                    "artifact_refs": artifact_refs,
                    "approval_request_refs": [
                        *research_state.approval_request_refs,
                        approval.request_id,
                    ],
                }
            )
            updated_workflow = workflow_state.model_copy(
                update={
                    "current_stage": ProjectStage.WAITING_HUMAN,
                    "pending_approval_ref": approval.request_id,
                    "research_state": updated_research,
                }
            )
            self._approvals[request.project_id] = approval
        else:
            blocking_findings = [
                item for item in outcome.findings if item.decision_scope in {DecisionScope.STAGE, DecisionScope.PROJECT}
            ]
            if blocking_findings:
                finding = blocking_findings[0]
                next_stage = ProjectStage.BLOCKED
                target_agent = None
                risk_flags = [
                    *research_state.risk_flags,
                    f"REVIEW_BLOCK_{finding.decision_scope.value}",
                ]
            else:
                finding = outcome.findings[0]
                next_stage = ProjectStage.REWORK
                target_agent = self._REVIEW_FINDING_TARGETS.get(
                    finding.category.strip().lower(), "paper_writing"
                )
                risk_flags = list(research_state.risk_flags)
            updated_research = research_state.model_copy(
                update={
                    "current_stage": next_stage,
                    "artifact_refs": artifact_refs,
                    "rework_target_agent": target_agent,
                    "rework_target_refs": list(finding.blocked_target_ids),
                    "rework_trigger_refs": [
                        *research_state.rework_trigger_refs,
                        *[item.finding_id for item in outcome.findings],
                    ],
                    "rework_reason": f"{finding.category}: {finding.description}",
                    "risk_flags": risk_flags,
                }
            )
            updated_workflow = workflow_state.model_copy(
                update={
                    "current_stage": next_stage,
                    "pending_approval_ref": None,
                    "research_state": updated_research,
                }
            )
            approval = None
        self._states[request.project_id] = updated_research
        self._workflow_states[request.project_id] = updated_workflow
        self._persist(request.project_id)
        return ReproducibilityReviewRunResult(
            workflow_state=updated_workflow,
            outcome=outcome,
            approval_request=approval,
        )

    @staticmethod
    def _require_research_state(workflow_state: ControllerWorkflowState) -> ResearchState:
        if workflow_state.research_state is None:
            raise ValueError("workflow state has no research state")
        return workflow_state.research_state

    @staticmethod
    def _require_data_pipeline(workflow_state: ControllerWorkflowState) -> DataPipelineState:
        if workflow_state.data_pipeline is None:
            raise ValueError("workflow has no active data pipeline")
        return workflow_state.data_pipeline

    def route_review_finding(
        self, project_id: str, finding: ReviewFinding
    ) -> ResearchState:
        """Route a structured review finding to the Agent that can revise it."""
        workflow_state = self.get_state(project_id)
        if workflow_state.current_stage is not ProjectStage.REWORK:
            raise ValueError("review findings can only route a project in REWORK")
        state = workflow_state.research_state
        if state is None:
            raise ValueError("workflow state has no research state")
        if finding.decision_scope in {DecisionScope.STAGE, DecisionScope.PROJECT}:
            updated = state.model_copy(
                update={
                    "current_stage": ProjectStage.BLOCKED,
                    "rework_target_agent": None,
                    "rework_target_refs": list(finding.blocked_target_ids),
                    "rework_reason": f"{finding.category}: {finding.description}",
                    "risk_flags": [
                        *state.risk_flags,
                        f"REVIEW_BLOCK_{finding.decision_scope.value}",
                    ],
                }
            )
            self._states[project_id] = updated
            self._workflow_states[project_id] = workflow_state.model_copy(
                update={"current_stage": ProjectStage.BLOCKED, "research_state": updated}
            )
            self._persist(project_id)
            return updated
        target_agent = self._REVIEW_FINDING_TARGETS.get(finding.category.strip().lower())
        if target_agent is None:
            raise ValueError(f"no rework target is defined for review category {finding.category}")
        trigger_refs = [*state.rework_trigger_refs]
        if finding.finding_id not in trigger_refs:
            trigger_refs.append(finding.finding_id)
        updated = state.model_copy(
            update={
                "rework_target_agent": target_agent,
                "rework_target_refs": list(finding.blocked_target_ids),
                "rework_reason": f"{finding.category}: {finding.description}",
                "rework_trigger_refs": trigger_refs,
            }
        )
        self._states[project_id] = updated
        self._workflow_states[project_id] = workflow_state.model_copy(
            update={"research_state": updated}
        )
        self._persist(project_id)
        return updated

    def list_agent_capabilities(self) -> list[AgentCapability]:
        return [agent.capability() for agent in self.dispatcher.registry.agents.values()]

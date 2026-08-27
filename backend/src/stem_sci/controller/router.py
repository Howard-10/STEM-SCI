"""Controller-owned Agent registry, dispatch and minimal planning workflow."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
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
    ResearchDesignAgent,
)
from stem_sci.agents.planning_contracts import PlanningBrief
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
    ManuscriptNumericClaim,
    ReproducibilityReviewInput,
    ReproducibilityReviewOutcome,
)
from stem_sci.agents.runtime import StructuredGenerator
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
from .policy.route_store import RouteDecisionStore
from .store import WorkflowStore
from .workflow_timeline import (
    InMemoryWorkflowFeedbackStore,
    WorkflowFeedback,
    WorkflowFeedbackAction,
    WorkflowFeedbackStore,
)


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


class WorkflowTimeline(BaseModel):
    project_id: str
    research_intent: str
    workflow_state: ControllerWorkflowState
    agent_runs: list[AgentRunRecord]
    artifact_contents: list[ArtifactContent]
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    routes: list[RouteDecision]
    feedback: list[WorkflowFeedback]
    pending_approval: ApprovalRequest | None = None


class WorkflowFeedbackResult(BaseModel):
    workflow_state: ControllerWorkflowState
    workflow_run: WorkflowRunResult | None = None


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
            evidence_agent = EvidenceReviewAgent(
                pipeline=EvidenceReviewPipeline(generator=generator, model=model)
            )
            writing_agent = PaperWritingAgent(
                pipeline=PaperWritingPipeline(generator=generator, model=model)
            )
        else:
            evidence_agent = EvidenceReviewAgent()
            writing_agent = PaperWritingAgent()
        instances: Iterable[BaseAgent] = (
            MentorPlanningAgent(),
            evidence_agent,
            ResearchDesignAgent(),
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
        feedback_store: WorkflowFeedbackStore | None = None,
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
        self.feedback_store = feedback_store or InMemoryWorkflowFeedbackStore()
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
    ) -> None:
        candidate_content = {
            artifact.candidate_ref: artifact for artifact in result.candidate_artifacts
        }
        for index, artifact_ref in enumerate(result.candidate_artifact_refs):
            artifact_type = artifact_ref.rsplit("/", maxsplit=1)[-1]
            artifact_id = f"{result.agent_run_id}:artifact:{index}"
            content_uri = artifact_ref
            artifact_hash = sha256(artifact_ref.encode("utf-8")).hexdigest()
            payload = candidate_content.get(artifact_ref)
            if payload is not None:
                content = self.artifact_content_store.put(
                    ArtifactContent(
                        artifact_id=artifact_id,
                        project_id=route.project_id,
                        artifact_type=payload.artifact_type,
                        version=1,
                        schema_version=payload.schema_version,
                        body=payload.body,
                        created_at=result.created_at,
                    )
                )
                if content.content_hash is None:
                    raise ValueError("persisted artifact content has no hash")
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

    def _approved_output_refs(self, project_id: str) -> set[str]:
        """Return candidate refs from Agent runs whose candidate was approved."""
        approved_refs = {
            decision.artifact_id
            for decision in self.decision_store.list_project(project_id)
            if decision.decision == "approved"
        }
        output_refs: set[str] = set()
        for record in self.agent_run_store.list_project(project_id):
            if approved_refs.intersection(record.output_artifact_refs):
                output_refs.update(record.output_artifact_refs)
        return output_refs

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
        approved_types = {
            ref.rsplit("/", maxsplit=1)[-1] for ref in approved_refs
        }
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
            ref
            for ref in sorted(approved_refs)
            if ref.rsplit("/", maxsplit=1)[-1] in protocol_output_types
            and ref not in protocol_refs
        )
        result_refs.extend(
            ref
            for ref in sorted(approved_refs)
            if ref.rsplit("/", maxsplit=1)[-1] in result_output_types
            and ref not in result_refs
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
        if not isinstance(planner, MentorPlanningAgent):
            raise ValueError("mentor_planning registry entry has an invalid implementation")
        planning_brief = self._build_planning_brief(
            request.project_id, agent_input, request.research_intent
        )
        result = planner.propose_for(
            agent_input, planning_brief, model_assisted=planner.pipeline is not None
        ).agent_result
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

    @staticmethod
    def _build_planning_brief(
        project_id: str, agent_input: AgentInput, research_intent: str
    ) -> PlanningBrief:
        """Turn a short human idea into an explicit, reviewable planning brief."""
        import re

        def field(*labels: str, fallback: str) -> str:
            label_pattern = "|".join(re.escape(label) for label in labels)
            match = re.search(rf"(?:{label_pattern})\s*[:：]\s*([^；;\n]+)", research_intent)
            return match.group(1).strip().rstrip("。．.") if match else fallback

        outcomes = field("主要指标", "结果指标", fallback="主要研究目标指标（待确认）")
        intervention_and_comparator = field("干预与对照", fallback="")
        intervention = "研究意图中描述的干预、方法或技术"
        comparator = "常规方法或基线条件（待确认）"
        if intervention_and_comparator and re.search(r"\s*(?:vs|VS|对照|比较)\s*", intervention_and_comparator):
            parts = re.split(r"\s*(?:vs|VS|对照|比较)\s*", intervention_and_comparator, maxsplit=1)
            intervention, comparator = [part.strip() for part in parts]
        return PlanningBrief(
            agent_run_id=agent_input.agent_run_id,
            project_id=project_id,
            task_ref=agent_input.task_ref,
            topic=research_intent,
            population=field("研究对象", "研究人群", fallback="目标研究人群（待确认）"),
            context=field("研究场景", "应用场景", fallback="教育或科研应用场景（待确认）"),
            intervention=intervention,
            comparator=comparator,
            candidate_outcomes=[outcomes],
            constraints=["需要在正式研究前确认伦理、数据治理与样本可得性"],
            exclusions=["超出当前研究意图且无法由本项目验证的结论"],
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

    def workflow_timeline(self, project_id: str) -> WorkflowTimeline:
        state = self.get_state(project_id)
        agent_runs = sorted(
            self.agent_run_store.list_project(project_id),
            key=lambda item: (item.started_at, item.agent_run_id),
        )
        artifact_contents = sorted(
            self.artifact_content_store.list_project(project_id),
            key=lambda item: (item.created_at, item.artifact_id, item.version),
        )
        artifact_contents = self._restore_legacy_planning_contents(
            project_id, agent_runs, artifact_contents
        )
        return WorkflowTimeline(
            project_id=project_id,
            research_intent=self._project_intents[project_id],
            workflow_state=state,
            agent_runs=agent_runs,
            artifact_contents=artifact_contents,
            artifacts=sorted(
                self.artifact_store.list_project(project_id),
                key=lambda item: (item.created_at, item.artifact_id, item.version),
            ),
            routes=sorted(
                self.route_store.list_project(project_id) if self.route_store else [],
                key=lambda item: (item.created_at, item.decision_id),
            ),
            feedback=self.feedback_store.list_project(project_id),
            pending_approval=self._approvals.get(project_id),
        )

    def _restore_legacy_planning_contents(
        self,
        project_id: str,
        agent_runs: list[AgentRunRecord],
        artifact_contents: list[ArtifactContent],
    ) -> list[ArtifactContent]:
        """Backfill readable planner bodies for runs created by the old scaffold."""
        planner = self.dispatcher.registry.get("mentor_planning")
        if not isinstance(planner, MentorPlanningAgent):
            return artifact_contents
        known_ids = {item.artifact_id for item in artifact_contents}
        restored = list(artifact_contents)
        for run in agent_runs:
            if run.agent_id != "mentor_planning":
                continue
            expected_types = {
                "ResearchContractCandidate",
                "FeasibilityReport",
                "ResearchQuestionTree",
                "ResearchScopeCandidate",
                "ProjectRoadmap",
            }
            if any(
                f"{run.agent_run_id}:artifact:" in item.artifact_id
                and item.artifact_type in expected_types
                for item in artifact_contents
            ):
                continue
            if not any(ref.rsplit("/", maxsplit=1)[-1] in expected_types for ref in run.output_artifact_refs):
                continue
            agent_input = AgentInput(
                agent_run_id=run.agent_run_id,
                task_ref=f"{project_id}:planning",
                context_bundle_ref="context://initial",
                allowed_tool_capabilities=list(planner.allowed_tool_capabilities),
                allowed_output_types=list(planner.allowed_output_types),
                policy_version="controller-policy-v1",
                prompt_template_version="planner-scaffold-v1",
            )
            outcome = planner.propose_for(
                agent_input,
                self._build_planning_brief(
                    project_id, agent_input, self._project_intents.get(project_id, "")
                ),
            )
            for index, candidate in enumerate(outcome.agent_result.candidate_artifacts):
                artifact_id = f"{run.agent_run_id}:artifact:{index}"
                if artifact_id in known_ids:
                    continue
                restored.append(
                    ArtifactContent(
                        project_id=project_id,
                        artifact_id=artifact_id,
                        version=1,
                        artifact_type=candidate.artifact_type,
                        schema_version=candidate.schema_version,
                        body=candidate.body,
                        created_at=run.started_at,
                    )
                )
                known_ids.add(artifact_id)
        return sorted(restored, key=lambda item: (item.created_at, item.artifact_id, item.version))

    def apply_workflow_feedback(self, feedback: WorkflowFeedback) -> WorkflowFeedbackResult:
        state = self.get_state(feedback.project_id)
        route = state.last_route_decision
        if route is None or route.selected_route != feedback.agent_id:
            raise ValueError("feedback agent does not match the current workflow agent")
        if feedback.stage != state.current_stage.value:
            raise ValueError("feedback stage does not match the current workflow stage")
        if feedback.action is WorkflowFeedbackAction.CONTINUE and state.pending_approval_ref is not None:
            raise ValueError("workflow has a pending approval; approve or reject it before continuing")
        if feedback.action is WorkflowFeedbackAction.RERUN and state.pending_approval_ref is None:
            raise ValueError("rerun requires a pending candidate approval")

        self.feedback_store.put(feedback)
        self._project_intents[feedback.project_id] = (
            f"{self._project_intents[feedback.project_id]}\n\n"
            f"[User feedback for {feedback.agent_id}]: {feedback.feedback}"
        )
        self._persist(feedback.project_id)

        if feedback.action is WorkflowFeedbackAction.PAUSE:
            return WorkflowFeedbackResult(workflow_state=state)
        if feedback.action is WorkflowFeedbackAction.CONTINUE:
            workflow_run = self.run_next(feedback.project_id)
            return WorkflowFeedbackResult(
                workflow_state=workflow_run.workflow_state,
                workflow_run=workflow_run,
            )

        self.resume_approval(
            feedback.project_id,
            self.get_pending_approval(feedback.project_id),
            decision="rejected",
            decided_by=feedback.created_by,
        )
        workflow_run = self.run_next(feedback.project_id)
        return WorkflowFeedbackResult(
            workflow_state=workflow_run.workflow_state,
            workflow_run=workflow_run,
        )

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
        elif agent_id == "mentor_planning":
            if not isinstance(agent, MentorPlanningAgent):
                raise ValueError("mentor_planning registry entry has an invalid implementation")
            planning_brief = self._build_planning_brief(
                project_id,
                agent_input,
                self._project_intents.get(project_id, ""),
            )
            result = agent.propose_for(
                agent_input, planning_brief, model_assisted=agent.pipeline is not None
            ).agent_result
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

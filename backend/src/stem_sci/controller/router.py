"""Controller-owned Agent registry, dispatch and minimal planning workflow."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
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
from stem_sci.agents.base import BaseAgent
from stem_sci.agents.contracts import ApprovalRequest, ReviewFinding
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
from stem_sci.controller.policy.route_decision import RouteDecision
from stem_sci.core.enums import DecisionScope, ProjectStage, TaskStatus
from stem_sci.core.models import ApprovalRecord
from stem_sci.core.reducers import merge_references
from stem_sci.core.state import ResearchState
from stem_sci.operators.executor import OperatorExecutor
from stem_sci.provenance.agent_run_store import AgentRunStore, InMemoryAgentRunStore
from stem_sci.provenance.models import AgentRunRecord

from .merger import validate_agent_result
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


@dataclass(frozen=True)
class AgentRegistry:
    """Controller-owned mapping from stable agent ids to role implementations."""

    agents: Mapping[str, BaseAgent]

    @classmethod
    def default(cls) -> AgentRegistry:
        instances: Iterable[BaseAgent] = (
            MentorPlanningAgent(),
            EvidenceReviewAgent(),
            ResearchDesignAgent(),
            DataAnalysisAgent(),
            PaperWritingAgent(),
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
        context_bundle: ContextBundle | None = None,
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
        ProjectStage.DATA_READY: (
            "data_analysis",
            "analysis_execution",
            "audit_data",
            "frozen dataset and analysis plan",
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

    def _execute_agent_tools(
        self, project_id: str, result: AgentResult
    ) -> tuple[list[str], list[str]]:
        runs = self.operator_executor.execute_tool_requests(
            project_id=project_id,
            agent_run_id=result.agent_run_id,
            tool_requests=result.tool_requests,
        )
        execution_refs = [run.operator_run_id for run in runs]
        risk_flags: list[str] = []
        if any(run.status.value == "BLOCKED" for run in runs):
            risk_flags.append("OPERATOR_EXECUTION_UNAVAILABLE")
        if any(run.status.value == "FAILED" for run in runs):
            risk_flags.append("OPERATOR_REQUEST_FAILED")
        return execution_refs, risk_flags

    def _record_audit(
        self,
        agent_input: AgentInput,
        result: AgentResult,
        route: RouteDecision,
        execution_refs: list[str],
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
                output_artifact_refs=list(result.candidate_artifact_refs),
                tool_run_refs=execution_refs,
                llm_metadata_refs=result.llm_metadata_refs,
                route_decision_ref=route.decision_id,
                started_at=result.created_at,
                finished_at=result.created_at,
            )
        )
        if self.route_store is not None:
            self.route_store.put(route)

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
        execution_refs, operator_risk_flags = self._execute_agent_tools(request.project_id, result)

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
            artifact_refs=result.candidate_artifact_refs,
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
        self._record_audit(agent_input, result, route, execution_refs)
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
        context_bundle: ContextBundle | None = None
        if agent_id == "evidence_review" and self.context_provider is not None:
            context_bundle = self.context_provider.build_context(
                project_id=project_id,
                task_ref=f"{project_id}:{task_type}",
                query=self._project_intents.get(project_id, ""),
                token_budget=2_000,
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
            required_context=[context_bundle.context_id] if context_bundle else [required_context],
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
            context_bundle_ref=f"context://{project_id}/{state.current_stage.lower()}",
            allowed_tool_capabilities=list(agent.allowed_tool_capabilities),
            allowed_output_types=list(agent.allowed_output_types),
            policy_version=route.policy_version,
            prompt_template_version=f"{agent_id}-scaffold-v1",
        )
        result = self.dispatcher.dispatch(agent_id, agent_input, context_bundle)
        if not result.candidate_artifact_refs:
            raise ValueError(f"{agent_id} produced no candidate artifacts")
        execution_refs, operator_risk_flags = self._execute_agent_tools(project_id, result)
        self._record_audit(agent_input, result, route, execution_refs)
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
            artifact_refs=result.candidate_artifact_refs,
            execution_run_refs=execution_refs,
            evidence_refs=result.evidence_refs,
            context_bundle_refs=[context_bundle.context_id] if context_bundle else [],
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
            next_stage = {
                "research_scope": ProjectStage.SCOPED,
                "evidence_protocol": ProjectStage.EVIDENCE_READY,
                "study_protocol": ProjectStage.STUDY_PROTOCOL_APPROVED,
                "analysis_specification": ProjectStage.ANALYZED,
                "analysis_execution": ProjectStage.ANALYZED,
                "manuscript": ProjectStage.DRAFTED,
                "review_report": ProjectStage.VERIFIED,
            }.get(approval_request.approval_type, ProjectStage.REWORK)
        updated = merge_references(
            state,
            task_status={"approval": TaskStatus.DONE},
            progress_ledger=[f"approval {approval_request.request_id}: {decision}"],
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
        next_workflow = workflow_state.model_copy(
            update={"current_stage": next_stage, "pending_approval_ref": None, "research_state": updated}
        )
        self._states[project_id] = updated
        self._workflow_states[project_id] = next_workflow
        self._approvals.pop(project_id, None)
        self._persist(project_id)
        return updated

    def get_pending_approval(self, project_id: str) -> ApprovalRequest:
        if project_id not in self._approvals:
            self._restore(project_id)
        try:
            return self._approvals[project_id]
        except KeyError as exc:
            raise ValueError(f"project has no pending approval: {project_id}") from exc

    def route_review_finding(
        self, project_id: str, finding: ReviewFinding
    ) -> ResearchState:
        """Route a structured review finding to the Agent that can revise it."""
        workflow_state = self.get_state(project_id)
        if workflow_state.current_stage is not ProjectStage.REWORK:
            raise ValueError("review findings can only route a project in REWORK")
        target_agent = self._REVIEW_FINDING_TARGETS.get(finding.category.strip().lower())
        if target_agent is None:
            raise ValueError(f"no rework target is defined for review category {finding.category}")
        state = workflow_state.research_state
        if state is None:
            raise ValueError("workflow state has no research state")
        trigger_refs = [*state.rework_trigger_refs]
        if finding.finding_id not in trigger_refs:
            trigger_refs.append(finding.finding_id)
        updated = state.model_copy(
            update={
                "rework_target_agent": target_agent,
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

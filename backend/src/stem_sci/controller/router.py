"""Controller-owned Agent registry, dispatch and minimal planning workflow."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from stem_sci.agents import (
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
from stem_sci.agents.contracts import ApprovalRequest

from .merger import validate_agent_result


class ProjectStage(str):
    """Small stage set for the first vertical slice."""

    INTAKE = "INTAKE"
    WAITING_HUMAN = "WAITING_HUMAN"
    SCOPED = "SCOPED"
    REWORK = "REWORK"


class ControllerWorkflowState(BaseModel):
    """Reference-only state owned and changed by the Controller."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)
    current_stage: str = ProjectStage.INTAKE
    pending_approval_ref: str | None = None
    last_agent_run_id: str | None = None


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


@dataclass(frozen=True)
class AgentRegistry:
    """Controller-owned mapping from stable agent ids to role implementations."""

    agents: Mapping[str, BaseAgent]

    @classmethod
    def default(cls) -> "AgentRegistry":
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

    def dispatch(self, agent_id: str, agent_input: AgentInput) -> AgentResult:
        agent = self.registry.get(agent_id)
        result = agent.run(agent_input)
        return validate_agent_result(result, agent.capability())


class ResearchController:
    """Minimal Controller slice: research idea -> planning candidate -> human wait."""

    def __init__(self, dispatcher: AgentDispatcher | None = None) -> None:
        self.dispatcher = dispatcher or AgentDispatcher()

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

        approval = ApprovalRequest(
            request_id=f"approval-{request.run_id}",
            artifact_ref=result.candidate_artifact_refs[0],
            approval_type="research_scope",
            reason="Confirm the candidate research scope before evidence retrieval.",
            risk_summary="The Agent output is a proposal and has not been human approved.",
        )
        state = ControllerWorkflowState(
            project_id=request.project_id,
            current_stage=ProjectStage.WAITING_HUMAN,
            pending_approval_ref=approval.request_id,
            last_agent_run_id=result.agent_run_id,
        )
        return PlanningRunResult(
            workflow_state=state,
            agent_result=result,
            approval_request=approval,
        )

    def approve_planning(
        self, state: ControllerWorkflowState, approval_request: ApprovalRequest
    ) -> ControllerWorkflowState:
        """Controller-only transition used after a human approves the scope."""
        if state.pending_approval_ref != approval_request.request_id:
            raise ValueError("approval request does not match the pending Controller decision")
        return state.model_copy(
            update={"current_stage": ProjectStage.SCOPED, "pending_approval_ref": None}
        )

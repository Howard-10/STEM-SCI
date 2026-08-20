"""LangGraph orchestration for the six-agent research workflow."""

from __future__ import annotations

from operator import add
from typing import Annotated, Literal, TypedDict, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from stem_sci.agents import ApprovalRequest
from stem_sci.controller.data_pipeline import DataPipelineState
from stem_sci.core.enums import ProjectStage

from .router import PlanningRequest, PlanningRunResult, ResearchController, WorkflowRunResult


class LangGraphWorkflowState(TypedDict, total=False):
    """Serializable orchestration state carried between graph nodes."""

    project_id: str
    research_intent: str
    current_stage: str
    selected_agent: str
    agent_results: Annotated[list[dict[str, object]], add]
    approval: dict[str, object]
    approval_decision: str
    approval_actor: str
    last_run: dict[str, object]
    final_stage: str
    workflow_status: str
    agent_chain_complete: bool
    validated_result_available: bool
    data_pipeline_stage: str | None


class LangGraphWorkflow:
    """Compile and invoke the Controller-backed six-agent StateGraph."""

    def __init__(self, controller: ResearchController | None = None) -> None:
        self.controller = controller or ResearchController()
        self.checkpointer = MemorySaver()
        graph = StateGraph(LangGraphWorkflowState)
        graph.add_node("start_planning", self._start_planning)
        graph.add_node("route_agent", self._route_agent)
        graph.add_node("await_approval", self._await_approval)
        graph.add_node("apply_approval", self._apply_approval)
        graph.add_node("finish", self._finish)
        graph.add_edge(START, "start_planning")
        graph.add_conditional_edges("start_planning", self._after_start, {
            "await_approval": "await_approval", "finish": "finish"
        })
        graph.add_conditional_edges("route_agent", self._after_route, {
            "await_approval": "await_approval", "finish": "finish"
        })
        graph.add_edge("await_approval", "apply_approval")
        graph.add_conditional_edges("apply_approval", self._after_approval, {
            "route_agent": "route_agent", "finish": "finish"
        })
        graph.add_edge("finish", END)
        self.graph = graph.compile(checkpointer=self.checkpointer)

    def start(self, request: PlanningRequest, *, thread_id: str | None = None) -> dict[str, object]:
        """Start a graph run and pause at human approval."""
        config: RunnableConfig = {"configurable": {"thread_id": thread_id or request.project_id}}
        state: LangGraphWorkflowState = {
            "project_id": request.project_id,
            "research_intent": request.research_intent,
            "current_stage": ProjectStage.INTAKE.value,
            "agent_results": [],
        }
        return cast(dict[str, object], self.graph.invoke(state, config))

    def resume(
        self,
        project_id: str,
        *,
        decision: Literal["approved", "rejected"],
        decided_by: str,
        thread_id: str | None = None,
    ) -> dict[str, object]:
        """Resume a paused graph using its checkpoint thread."""
        config: RunnableConfig = {"configurable": {"thread_id": thread_id or project_id}}
        return cast(dict[str, object], self.graph.invoke(
            Command(resume={"decision": decision, "decided_by": decided_by}), config
        ))

    def _start_planning(self, state: LangGraphWorkflowState) -> dict[str, object]:
        run = self.controller.start_planning(PlanningRequest(
            project_id=state["project_id"],
            research_intent=state["research_intent"],
            run_id=f"planning-{state['project_id']}",
        ))
        return self._run_update(run)

    def _route_agent(self, state: LangGraphWorkflowState) -> dict[str, object]:
        return self._run_update(self.controller.run_next(state["project_id"]))

    def _await_approval(self, state: LangGraphWorkflowState) -> dict[str, object]:
        response = interrupt({
            "type": "human_approval_required",
            "project_id": state["project_id"],
            "agent_id": state["selected_agent"],
            "approval": state["approval"],
        })
        if not isinstance(response, dict) or response.get("decision") not in {"approved", "rejected"}:
            raise ValueError("LangGraph approval resume must contain approved or rejected decision")
        return {
            "approval_decision": response["decision"],
            "approval_actor": str(response.get("decided_by", "unknown")),
        }

    def _apply_approval(self, state: LangGraphWorkflowState) -> dict[str, object]:
        updated = self.controller.resume_approval(
            state["project_id"],
            ApprovalRequest.model_validate(state["approval"]),
            decision=state["approval_decision"],
            decided_by=state["approval_actor"],
        )
        return {"current_stage": updated.current_stage.value, "approval": {}}

    def _finish(self, state: LangGraphWorkflowState) -> dict[str, object]:
        validated = self._validated_result_available(state)
        current_stage = state.get("current_stage", ProjectStage.INTAKE.value)
        verified = current_stage == ProjectStage.VERIFIED.value
        return {
            "final_stage": current_stage,
            "workflow_status": (
                "VERIFIED_WITH_VALIDATED_RESULTS" if verified and validated
                else "AGENT_CHAIN_COMPLETE_REQUIRES_DATA_VALIDATION" if verified
                else current_stage
            ),
            "agent_chain_complete": verified,
            "validated_result_available": validated,
            "data_pipeline_stage": self._data_pipeline_stage(state),
        }

    def _controller_data_pipeline(self, state: LangGraphWorkflowState) -> DataPipelineState | None:
        try:
            return self.controller.get_state(state["project_id"]).data_pipeline
        except ValueError:
            return None

    def _validated_result_available(self, state: LangGraphWorkflowState) -> bool:
        pipeline = self._controller_data_pipeline(state)
        return bool(
            pipeline and pipeline.validation_report and pipeline.validation_report.passed
            and pipeline.statistical_result_card
        )

    def _data_pipeline_stage(self, state: LangGraphWorkflowState) -> str | None:
        pipeline = self._controller_data_pipeline(state)
        return pipeline.stage.value if pipeline else None

    @staticmethod
    def _run_update(run: PlanningRunResult | WorkflowRunResult) -> dict[str, object]:
        agent_result = run.agent_result
        workflow_state = run.workflow_state
        approval = run.approval_request
        return {
            "current_stage": workflow_state.current_stage.value,
            "selected_agent": agent_result.agent_id,
            "agent_results": [agent_result.model_dump(mode="json")],
            "approval": approval.model_dump(mode="json"),
            "last_run": {
                "agent_id": agent_result.agent_id,
                "agent_run_id": agent_result.agent_run_id,
            },
        }

    @staticmethod
    def _after_start(state: LangGraphWorkflowState) -> str:
        return "await_approval" if state.get("approval") else "finish"

    @staticmethod
    def _after_route(state: LangGraphWorkflowState) -> str:
        return "await_approval" if state.get("approval") else "finish"

    @staticmethod
    def _after_approval(state: LangGraphWorkflowState) -> str:
        if state.get("approval_decision") == "rejected":
            return "route_agent"
        return "finish" if state.get("current_stage") == ProjectStage.VERIFIED.value else "route_agent"


__all__ = ["LangGraphWorkflow", "LangGraphWorkflowState"]

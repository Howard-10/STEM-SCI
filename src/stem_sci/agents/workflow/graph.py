from __future__ import annotations

from typing import Any

try:
    from langgraph.graph import END, START, StateGraph
except ImportError as exc:  # pragma: no cover - handled at runtime
    END = "__end__"
    START = "__start__"
    StateGraph = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

from .mock_agents import (
    DEFAULT_AGENT_REGISTRY,
    AgentRegistry,
    is_collaboration_request,
    is_research_collaboration_request,
    is_research_design_request,
    is_mentor_planning_request,
    is_tool_request,
)
from .protocol import AgentInput, AgentOutput, WorkflowState
from .utils import deduplicate_sources, error_response, normalize_request, normalize_response

_LOW_CONFIDENCE_THRESHOLD = 0.75


def _ensure_langgraph_installed() -> None:
    if _IMPORT_ERROR is not None or StateGraph is None:
        raise RuntimeError(
            "langgraph is not installed. Run `pip install -r requirements.txt` before executing the workflow."
        ) from _IMPORT_ERROR


def _append_trace(state: WorkflowState, step: str) -> list[str]:
    return [*state.get("trace", []), step]


def _build_agent_input(state: WorkflowState) -> AgentInput:
    return {
        "query": state.get("query", ""),
        "history": state.get("history", []),
        "context": state.get("context", {"scene": "general", "user_profile": {}, "extra_params": {}}),
    }


def normalize_input_node(state: WorkflowState) -> WorkflowState:
    normalized_input = normalize_request(state.get("raw_input", {}))
    return {
        "query": normalized_input["query"],
        "history": normalized_input["history"],
        "context": normalized_input["context"],
        "escalated": False,
        "trace": _append_trace(state, "normalize_input"),
    }


def route_request_node(state: WorkflowState) -> WorkflowState:
    query = state.get("query", "")
    extra_params = state.get("context", {}).get("extra_params", {})

    if is_research_collaboration_request(query, extra_params):
        route = "research_collaboration"
    elif is_mentor_planning_request(query, extra_params):
        route = "mentor_planning"
    elif is_research_design_request(query, extra_params):
        route = "research_design"
    elif is_collaboration_request(query, extra_params):
        route = "collaboration"
    elif is_tool_request(query, extra_params):
        route = "tool"
    else:
        route = "knowledge"

    return {
        "route": route,
        "active_agent": "router",
        "trace": _append_trace(state, f"route:{route}"),
    }


def route_selector(state: WorkflowState) -> str:
    return state.get("route", "knowledge")


def make_knowledge_node(agent_registry: AgentRegistry):
    def knowledge_node(state: WorkflowState) -> WorkflowState:
        response = agent_registry.knowledge_agent(_build_agent_input(state))
        return {
            "primary_response": response,
            "knowledge_response": response,
            "active_agent": "knowledge_agent",
            "trace": _append_trace(state, "knowledge_agent"),
        }

    return knowledge_node


def make_tool_node(agent_registry: AgentRegistry):
    def tool_node(state: WorkflowState) -> WorkflowState:
        response = agent_registry.tool_agent(_build_agent_input(state))
        return {
            "primary_response": response,
            "tool_response": response,
            "active_agent": "tool_agent",
            "trace": _append_trace(state, "tool_agent"),
        }

    return tool_node


def make_mentor_planning_node(agent_registry: AgentRegistry):
    def mentor_planning_node(state: WorkflowState) -> WorkflowState:
        response = normalize_response(agent_registry.mentor_planning_agent(_build_agent_input(state)))
        return {
            "primary_response": response,
            "mentor_planning_response": response,
            "active_agent": "mentor_planning_agent",
            "trace": _append_trace(state, "mentor_planning_agent"),
        }

    return mentor_planning_node


def make_research_design_node(agent_registry: AgentRegistry):
    def research_design_node(state: WorkflowState) -> WorkflowState:
        response = normalize_response(agent_registry.research_design_agent(_build_agent_input(state)))
        return {
            "primary_response": response,
            "research_design_response": response,
            "active_agent": "research_design_agent",
            "trace": _append_trace(state, "research_design_agent"),
        }

    return research_design_node


def quality_gate_node(state: WorkflowState) -> WorkflowState:
    response = normalize_response(state.get("primary_response"))
    query = state.get("query", "")
    extra_params = state.get("context", {}).get("extra_params", {})
    needs_collaboration = response["status"] == "error" or response["confidence"] < _LOW_CONFIDENCE_THRESHOLD
    if not needs_collaboration and is_collaboration_request(query, extra_params):
        needs_collaboration = True
    return {
        "escalated": needs_collaboration,
        "trace": _append_trace(state, f"quality_gate:{'escalate' if needs_collaboration else 'finalize'}"),
    }


def post_quality_selector(state: WorkflowState) -> str:
    return "collaboration" if state.get("escalated") else "finalize"


def collaboration_plan_node(state: WorkflowState) -> WorkflowState:
    query = state.get("query", "")
    extra_params = state.get("context", {}).get("extra_params", {})
    plan = [
        "Collect the domain interpretation from the knowledge branch.",
        "Run tool reasoning if explicit calculation or statistics are involved.",
        "Merge both branches into one protocol-compliant final answer.",
    ]
    if is_research_collaboration_request(query, extra_params):
        plan = [
            "Generate a candidate research scope, question tree, and feasibility assessment.",
            "Translate the candidate scope into estimand, protocol, measurement, and analysis-plan artifacts.",
            "Keep all research artifacts in candidate status until Controller approval.",
        ]
    elif not is_tool_request(query, extra_params):
        plan[1] = "Skip heavy calculation and keep the tool branch as a lightweight verifier."
    return {
        "collaboration_plan": plan,
        "active_agent": "collaboration_planner",
        "trace": _append_trace(state, "collaboration_plan"),
    }


def make_collaboration_knowledge_node(agent_registry: AgentRegistry):
    def collaboration_knowledge_node(state: WorkflowState) -> WorkflowState:
        response = agent_registry.knowledge_agent(_build_agent_input(state))
        return {"knowledge_response": response, "trace": _append_trace(state, "collaboration_knowledge")}

    return collaboration_knowledge_node


def make_collaboration_tool_node(agent_registry: AgentRegistry):
    def collaboration_tool_node(state: WorkflowState) -> WorkflowState:
        query = state.get("query", "")
        extra_params = state.get("context", {}).get("extra_params", {})
        if is_tool_request(query, extra_params):
            response = agent_registry.tool_agent(_build_agent_input(state))
        else:
            response = normalize_response({
                "answer": "[Collaboration Tool Step] No explicit calculation was requested, so the tool branch ran as a no-op verifier.",
                "sources": [],
                "confidence": 0.7,
                "status": "success",
                "extra": {"tool_name": "noop_verifier(mock)", "tool_params": {"query": query}, "raw_output": {"skipped": True}},
            })
        return {"tool_response": response, "trace": _append_trace(state, "collaboration_tool")}

    return collaboration_tool_node


def make_research_planning_node(agent_registry: AgentRegistry):
    def research_planning_node(state: WorkflowState) -> WorkflowState:
        response = normalize_response(agent_registry.mentor_planning_agent(_build_agent_input(state)))
        return {
            "mentor_planning_response": response,
            "active_agent": "mentor_planning_agent",
            "trace": _append_trace(state, "collaboration_mentor_planning"),
        }

    return research_planning_node


def make_research_design_collaboration_node(agent_registry: AgentRegistry):
    def research_design_collaboration_node(state: WorkflowState) -> WorkflowState:
        response = normalize_response(agent_registry.research_design_agent(_build_agent_input(state)))
        return {
            "research_design_response": response,
            "active_agent": "research_design_agent",
            "trace": _append_trace(state, "collaboration_research_design"),
        }

    return research_design_collaboration_node


def collaboration_synthesize_node(state: WorkflowState) -> WorkflowState:
    plan = state.get("collaboration_plan", [])
    query = state.get("query", "")
    extra_params = state.get("context", {}).get("extra_params", {})

    if is_research_collaboration_request(query, extra_params):
        mentor = normalize_response(state.get("mentor_planning_response"))
        design = normalize_response(state.get("research_design_response"))
        final_response: AgentOutput = {
            "answer": (
                "Research collaboration produced a candidate mentor plan and candidate research design. "
                "The artifacts are not formal approvals and the preregistered analysis plan remains unfrozen."
            ),
            "sources": deduplicate_sources(mentor["sources"], design["sources"]),
            "confidence": round(min(0.97, (mentor["confidence"] + design["confidence"]) / 2 + 0.05), 2),
            "status": "success" if mentor["status"] == "success" and design["status"] == "success" else "error",
            "extra": {
                "sub_agent_traces": [
                    {"agent": "mentor_planning_agent", "result": mentor["answer"], "status": mentor["status"], "extra": mentor["extra"]},
                    {"agent": "research_design_agent", "result": design["answer"], "status": design["status"], "extra": design["extra"]},
                ],
                "candidate_artifact_refs": mentor["extra"].get("candidate_artifact_refs", []) + design["extra"].get("candidate_artifact_refs", []),
                "approval_requests": [mentor["extra"].get("approval_request", {}), design["extra"].get("approval_request", {})],
                "collaboration_rounds": 1,
                "plan": plan,
                "requires_controller_approval": True,
            },
        }
    else:
        knowledge_response = normalize_response(state.get("knowledge_response"))
        tool_response = normalize_response(state.get("tool_response"))
        synthesis_parts = [
            "[Mock Collaboration Agent] Combined result generated from multiple branches.",
            f"Knowledge branch: {knowledge_response['answer']}",
        ]
        if not tool_response.get("extra", {}).get("raw_output", {}).get("skipped"):
            synthesis_parts.append(f"Tool branch: {tool_response['answer']}")
        synthesis_parts.append("Final synthesis: combine factual grounding with any available numeric verification, then answer in one pass.")
        final_response = {
            "answer": "\n".join(synthesis_parts),
            "sources": deduplicate_sources(knowledge_response["sources"], tool_response["sources"]),
            "confidence": round(min(0.97, max(knowledge_response["confidence"], tool_response["confidence"]) + 0.04), 2),
            "status": "success",
            "extra": {
                "sub_agent_traces": [
                    {"agent": "knowledge_agent", "result": knowledge_response["answer"], "status": knowledge_response["status"]},
                    {"agent": "tool_agent", "result": tool_response["answer"], "status": tool_response["status"]},
                ],
                "collaboration_rounds": 1,
                "plan": plan,
            },
        }

    return {"primary_response": final_response, "final_response": final_response, "active_agent": "collaboration_agent", "trace": _append_trace(state, "collaboration_synthesize")}


def finalize_response_node(state: WorkflowState) -> WorkflowState:
    base_response = state.get("final_response") or state.get("primary_response") or error_response("No agent produced a valid response.")
    response = normalize_response(base_response)
    extra = dict(response["extra"])
    extra["workflow_route"] = state.get("route", "knowledge")
    extra["workflow_trace"] = _append_trace(state, "finalize_response")
    extra["active_agent"] = state.get("active_agent", "unknown")
    finalized_response: AgentOutput = {
        "answer": response["answer"] or "The workflow completed without a textual answer.",
        "sources": response["sources"],
        "confidence": response["confidence"],
        "status": response["status"],
        "extra": extra,
    }
    return {"final_response": finalized_response, "trace": extra["workflow_trace"]}


def build_workflow(agent_registry: AgentRegistry | None = None):
    _ensure_langgraph_installed()
    agent_registry = agent_registry or DEFAULT_AGENT_REGISTRY
    builder = StateGraph(WorkflowState)
    builder.add_node("normalize_input", normalize_input_node)
    builder.add_node("route_request", route_request_node)
    builder.add_node("knowledge_agent", make_knowledge_node(agent_registry))
    builder.add_node("tool_agent", make_tool_node(agent_registry))
    builder.add_node("mentor_planning_agent", make_mentor_planning_node(agent_registry))
    builder.add_node("research_design_agent", make_research_design_node(agent_registry))
    builder.add_node("quality_gate", quality_gate_node)
    builder.add_node("collaboration_plan", collaboration_plan_node)
    builder.add_node("collaboration_knowledge", make_collaboration_knowledge_node(agent_registry))
    builder.add_node("collaboration_tool", make_collaboration_tool_node(agent_registry))
    builder.add_node("collaboration_mentor_planning", make_research_planning_node(agent_registry))
    builder.add_node("collaboration_research_design", make_research_design_collaboration_node(agent_registry))
    builder.add_node("collaboration_synthesize", collaboration_synthesize_node)
    builder.add_node("finalize_response", finalize_response_node)

    builder.add_edge(START, "normalize_input")
    builder.add_edge("normalize_input", "route_request")
    builder.add_conditional_edges("route_request", route_selector, {
        "knowledge": "knowledge_agent",
        "tool": "tool_agent",
        "mentor_planning": "mentor_planning_agent",
        "research_design": "research_design_agent",
        "collaboration": "collaboration_plan",
        "research_collaboration": "collaboration_plan",
    })
    builder.add_edge("knowledge_agent", "quality_gate")
    builder.add_edge("tool_agent", "quality_gate")
    builder.add_edge("mentor_planning_agent", "finalize_response")
    builder.add_edge("research_design_agent", "finalize_response")
    builder.add_conditional_edges("quality_gate", post_quality_selector, {"collaboration": "collaboration_plan", "finalize": "finalize_response"})
    builder.add_conditional_edges(
        "collaboration_plan",
        lambda state: "research" if is_research_collaboration_request(state.get("query", ""), state.get("context", {}).get("extra_params", {})) else "general",
        {"research": "collaboration_mentor_planning", "general": "collaboration_knowledge"},
    )
    builder.add_edge("collaboration_mentor_planning", "collaboration_research_design")
    builder.add_edge("collaboration_research_design", "collaboration_synthesize")
    builder.add_edge("collaboration_knowledge", "collaboration_tool")
    builder.add_edge("collaboration_tool", "collaboration_synthesize")
    builder.add_edge("collaboration_synthesize", "finalize_response")
    builder.add_edge("finalize_response", END)
    return builder.compile()


def run_workflow_with_state(payload: dict[str, Any], agent_registry: AgentRegistry | None = None) -> WorkflowState:
    return build_workflow(agent_registry=agent_registry).invoke({"raw_input": payload})


def run_workflow(payload: dict[str, Any], agent_registry: AgentRegistry | None = None) -> AgentOutput:
    return normalize_response(run_workflow_with_state(payload, agent_registry=agent_registry).get("final_response"))

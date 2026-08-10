from __future__ import annotations

from typing import Any, Literal, TypedDict


class Message(TypedDict):
    role: str
    content: str


class AgentContext(TypedDict, total=False):
    scene: str
    user_profile: dict[str, Any]
    extra_params: dict[str, Any]


class AgentInput(TypedDict):
    query: str
    history: list[Message]
    context: AgentContext


class Source(TypedDict, total=False):
    title: str
    url: str
    type: str


class AgentOutput(TypedDict):
    answer: str
    sources: list[Source]
    confidence: float
    status: Literal["success", "error"]
    extra: dict[str, Any]


class WorkflowState(TypedDict, total=False):
    raw_input: dict[str, Any]
    query: str
    history: list[Message]
    context: AgentContext
    route: str
    active_agent: str
    escalated: bool
    trace: list[str]
    primary_response: AgentOutput
    knowledge_response: AgentOutput
    tool_response: AgentOutput
    mentor_planning_response: AgentOutput
    research_design_response: AgentOutput
    collaboration_plan: list[str]
    final_response: AgentOutput

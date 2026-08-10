from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from workflow.protocol import AgentInput, AgentOutput

from .knowledge import knowledge_agent
from .mentor_planning import MENTOR_PLANNING_AGENT, is_mentor_planning_request
from .research_design import RESEARCH_DESIGN_AGENT, is_research_collaboration_request, is_research_design_request
from .tool import tool_agent

AgentCallable = Callable[[AgentInput], AgentOutput]


@dataclass(frozen=True)
class AgentRegistry:
    knowledge_agent: AgentCallable = knowledge_agent
    tool_agent: AgentCallable = tool_agent
    mentor_planning_agent: AgentCallable = MENTOR_PLANNING_AGENT.run
    research_design_agent: AgentCallable = RESEARCH_DESIGN_AGENT.run


DEFAULT_AGENT_REGISTRY = AgentRegistry()


def is_tool_request(query: str, extra_params: dict[str, object] | None = None) -> bool:
    extra_params = extra_params or {}
    query_lower = query.lower()
    keywords = [
        "calculate", "sum", "average", "mean", "percent", "ratio", "trend", "score", "compute", "statistics",
        "\u8ba1\u7b97", "\u5e73\u5747", "\u6c42\u548c", "\u6bd4\u4f8b", "\u589e\u957f\u7387", "\u7edf\u8ba1",
    ]
    if extra_params.get("tool_name") or any(char in query for char in ["+", "-", "*", "/"]):
        return True
    return any(keyword in query_lower or keyword in query for keyword in keywords)


def is_research_request(query: str, extra_params: dict[str, object] | None = None) -> bool:
    return is_mentor_planning_request(query, extra_params) or is_research_design_request(query, extra_params)


def is_collaboration_request(query: str, extra_params: dict[str, object] | None = None) -> bool:
    query_lower = query.lower()
    keywords = ["compare", "plan", "strategy", "workflow", "and", "together", "\u5bf9\u6bd4", "\u65b9\u6848", "\u7b56\u7565", "\u540c\u65f6", "\u534f\u540c", "\u5de5\u4f5c\u6d41"]
    return is_research_collaboration_request(query, extra_params) or (any(keyword in query_lower or keyword in query for keyword in keywords) and (is_tool_request(query, extra_params) or len(query) > 25))

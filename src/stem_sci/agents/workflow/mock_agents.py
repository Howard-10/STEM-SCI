"""Backward-compatible imports; Agent implementations live in the top-level agents package."""

from agents.registry import (
    DEFAULT_AGENT_REGISTRY,
    AgentRegistry,
    is_collaboration_request,
    is_research_request,
    is_research_collaboration_request,
    is_research_design_request,
    is_mentor_planning_request,
    is_tool_request,
)
from agents.knowledge import knowledge_agent as mock_knowledge_agent
from agents.tool import extract_math_expression, tool_agent as mock_tool_agent

__all__ = [
    "AgentRegistry",
    "DEFAULT_AGENT_REGISTRY",
    "extract_math_expression",
    "is_collaboration_request",
    "is_mentor_planning_request",
    "is_research_collaboration_request",
    "is_research_design_request",
    "is_research_request",
    "is_tool_request",
    "mock_knowledge_agent",
    "mock_tool_agent",
]

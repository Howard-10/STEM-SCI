"""Mentor/planning Agent role boundary."""

from .base import BaseAgent


class MentorPlanningAgent(BaseAgent):
    agent_id = "mentor_planning"
    supported_task_types = ("scope_research", "build_research_roadmap", "assess_feasibility")
    allowed_tool_capabilities = ("literature_search_request",)
    allowed_output_types = (
        "ResearchContractCandidate",
        "FeasibilityReport",
        "ResearchQuestionTree",
        "ResearchScopeCandidate",
        "ProjectRoadmap",
        "LiteratureRequirementList",
        "InitialRiskProfile",
        "UnresolvedQuestionList",
    )

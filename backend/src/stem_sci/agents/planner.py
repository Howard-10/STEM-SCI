"""Mentor/planning Agent role boundary."""

from .base import BaseAgent


class MentorPlanningAgent(BaseAgent):
    agent_id = "mentor_planning"
    skill_ids = ("research_scope_planning@v1", "research_feasibility_assessment@v1")
    tool_ids = (
        "context_bundle_read@v1",
        "research_scope_validator@v1",
        "feasibility_checker@v1",
    )
    supported_task_types = ("scope_research", "build_research_roadmap", "assess_feasibility")
    allowed_tool_capabilities = (*tool_ids, "literature_search_request")
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

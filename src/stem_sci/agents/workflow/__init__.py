"""Workflow package with lazy public exports to keep agents and protocol decoupled."""

__all__ = [
    "AgentRegistry",
    "MentorPlanningAgent",
    "ResearchDesignAgent",
    "build_workflow",
    "mentor_planning_agent",
    "research_design_agent",
    "run_workflow",
    "run_workflow_with_state",
]


def __getattr__(name: str):
    if name in {"build_workflow", "run_workflow", "run_workflow_with_state"}:
        from .graph import build_workflow, run_workflow, run_workflow_with_state

        return {
            "build_workflow": build_workflow,
            "run_workflow": run_workflow,
            "run_workflow_with_state": run_workflow_with_state,
        }[name]
    if name == "AgentRegistry":
        from agents.registry import AgentRegistry

        return AgentRegistry
    if name in {"MentorPlanningAgent", "mentor_planning_agent"}:
        from agents.mentor_planning import MentorPlanningAgent, mentor_planning_agent

        return {"MentorPlanningAgent": MentorPlanningAgent, "mentor_planning_agent": mentor_planning_agent}[name]
    if name in {"ResearchDesignAgent", "research_design_agent"}:
        from agents.research_design import ResearchDesignAgent, research_design_agent

        return {"ResearchDesignAgent": ResearchDesignAgent, "research_design_agent": research_design_agent}[name]
    raise AttributeError(name)

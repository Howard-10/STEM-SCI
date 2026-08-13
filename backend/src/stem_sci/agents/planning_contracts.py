"""Proposal-only contracts for the mentor/planning Agent.

The planning role converts a human-supplied research brief into structured
*candidate* research objects.  It deliberately cannot approve a scope,
declare feasibility, or assert that a literature claim is true.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from stem_sci.agents.contracts import AgentContract, AgentResult


class PlanningBrief(AgentContract):
    """The minimum human-owned information needed to plan a study."""

    agent_run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    task_ref: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    population: str = Field(min_length=1)
    context: str = Field(min_length=1)
    intervention: str = Field(min_length=1)
    comparator: str = Field(min_length=1)
    candidate_outcomes: list[str] = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class FeasibilityReport(AgentContract):
    report_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    status: Literal["CANDIDATE_FEASIBLE", "NEEDS_SCOPING"]
    assumptions: list[str] = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    required_confirmations: list[str] = Field(min_length=1)


class ResearchQuestionTree(AgentContract):
    tree_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    primary_question: str = Field(min_length=1)
    secondary_questions: list[str] = Field(default_factory=list)
    out_of_scope_questions: list[str] = Field(default_factory=list)


class ProjectRoadmap(AgentContract):
    roadmap_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    milestones: list[str] = Field(min_length=1)
    human_decision_points: list[str] = Field(min_length=1)


class LiteratureRequirement(AgentContract):
    requirement_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    required_evidence_categories: list[str] = Field(min_length=1)
    screening_questions: list[str] = Field(min_length=1)
    minimum_verification_status: Literal["source_verified", "human_verified"] = "source_verified"


class InitialRiskProfile(AgentContract):
    profile_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    risks: list[str] = Field(min_length=1)
    mitigations: list[str] = Field(min_length=1)
    requires_human_confirmation: Literal[True] = True


class MentorPlanningOutcome(AgentContract):
    """A complete planning package, still awaiting gates and human approval."""

    agent_result: AgentResult
    feasibility_report: FeasibilityReport
    question_tree: ResearchQuestionTree
    roadmap: ProjectRoadmap
    literature_requirement: LiteratureRequirement
    risk_profile: InitialRiskProfile
    model_assisted_rationale: dict[str, object] | None = None

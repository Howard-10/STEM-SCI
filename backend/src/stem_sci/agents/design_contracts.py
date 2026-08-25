"""Proposal-only contracts for the research-design Agent.

The design role compiles a bounded study brief into a protocol candidate.  It
does not select participants, collect data, approve ethics, or freeze the
preregistered analysis plan.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from stem_sci.agents.contracts import AgentContract, AgentResult


class ResearchDesignBrief(AgentContract):
    agent_run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    task_ref: str = Field(min_length=1)
    research_contract_ref: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    population: str = Field(min_length=1)
    context: str = Field(min_length=1)
    intervention: str = Field(min_length=1)
    comparator: str = Field(min_length=1)
    primary_outcome: str = Field(min_length=1)
    secondary_outcomes: list[str] = Field(default_factory=list)
    design_type: Literal["randomized_parallel_repeated_measures", "candidate_crossover"]
    measurement_timepoints: list[str] = Field(min_length=1)
    sampling_approach: str = Field(min_length=1)
    ethics_ref: str = Field(min_length=1)
    confirmatory_model: str = Field(min_length=1)
    covariates: list[str] = Field(default_factory=list)
    exclusion_rules: list[str] = Field(default_factory=list)
    missing_data_strategy: str = Field(min_length=1)
    outlier_strategy: str = Field(min_length=1)
    analysis_mode: Literal["PYTHON_ONLY", "SPSS_PYTHON_DUAL"] = "PYTHON_ONLY"


class StudyProtocolCandidate(AgentContract):
    protocol_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    research_contract_ref: str = Field(min_length=1)
    design_type: str = Field(min_length=1)
    allocation_description: str = Field(min_length=1)
    primary_outcome: str = Field(min_length=1)
    measurement_timepoints: list[str] = Field(min_length=1)
    ethics_ref: str = Field(min_length=1)
    approval_required: Literal[True] = True


class AnalysisPlanDraft(AgentContract):
    """Pre-data candidate decisions; it is not an approved preregistration."""

    plan_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    primary_outcomes: list[str] = Field(min_length=1)
    secondary_outcomes: list[str] = Field(default_factory=list)
    confirmatory_models: list[str] = Field(min_length=1)
    covariates: list[str] = Field(default_factory=list)
    exclusion_rules: list[str] = Field(default_factory=list)
    missing_data_strategy: str = Field(min_length=1)
    outlier_strategy: str = Field(min_length=1)
    analysis_mode: Literal["PYTHON_ONLY", "SPSS_PYTHON_DUAL"]
    status: Literal["candidate"] = "candidate"
    requires_human_approval_before_data_collection: Literal[True] = True


class MeasurementPlanCandidate(AgentContract):
    plan_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    primary_outcome: str = Field(min_length=1)
    secondary_outcomes: list[str] = Field(default_factory=list)
    measurement_timepoints: list[str] = Field(min_length=1)
    data_dictionary_fields: list[str] = Field(min_length=1)


class ResearchDesignOutcome(AgentContract):
    agent_result: AgentResult
    study_protocol_candidate: StudyProtocolCandidate
    preregistered_analysis_plan_draft: AnalysisPlanDraft
    measurement_plan_candidate: MeasurementPlanCandidate
    model_assisted_rationale: dict[str, object] | None = None

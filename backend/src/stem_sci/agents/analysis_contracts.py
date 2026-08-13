"""Typed, proposal-only contracts for the data-analysis Agent.

These objects describe what deterministic operators should later do.  They
never carry raw records, executable code, or generated statistical numbers.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from stem_sci.agents.contracts import AgentContract, AgentResult
from stem_sci.statistics.mode_policy import AnalysisMode
from stem_sci.statistics.models import ExecutionStatus


class DataAnalysisPhase(StrEnum):
    PRE_ANALYSIS = "PRE_ANALYSIS"
    POST_EXECUTION_INTERPRETATION = "POST_EXECUTION_INTERPRETATION"


class DataAuditSpecification(AgentContract):
    """Rules a deterministic data-audit operator must evaluate."""

    specification_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    data_collection_schema_ref: str = Field(min_length=1)
    variable_dictionary_ref: str = Field(min_length=1)
    required_variables: list[str] = Field(min_length=1)
    missingness_checks: list[str] = Field(min_length=1)
    range_and_type_checks: list[str] = Field(min_length=1)
    privacy_checks: list[str] = Field(min_length=1)


class AnalysisReadinessReport(AgentContract):
    """Readiness assessment before any data operation is dispatched."""

    report_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    preregistered_plan_ref: str = Field(min_length=1)
    status: Literal["READY", "REWORK", "BLOCKED"]
    missing_requirements: list[str] = Field(default_factory=list)
    blocked_target_ids: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)


class DataProcessingPlanCandidate(AgentContract):
    """A human-approvable candidate, never a data mutation command."""

    candidate_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    data_audit_specification_ref: str = Field(min_length=1)
    proposed_steps: list[str] = Field(min_length=1)
    missing_data_strategy_ref: str = Field(min_length=1)
    exclusion_rule_refs: list[str] = Field(default_factory=list)
    requires_human_approval: Literal[True] = True


class ExecutableAnalysisPlanCandidate(AgentContract):
    """Schema mapping proposal that cannot alter preregistered decisions."""

    candidate_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    preregistered_plan_ref: str = Field(min_length=1)
    data_collection_schema_ref: str = Field(min_length=1)
    variable_mapping: dict[str, str] = Field(default_factory=dict)
    type_confirmations: dict[str, str] = Field(default_factory=dict)
    software_configuration: dict[str, str] = Field(default_factory=dict)
    analysis_mode: AnalysisMode
    model_specification_refs: list[str] = Field(min_length=1)


class CodeSpecificationDraft(AgentContract):
    """A draft input for the coding operator; it contains no source code."""

    draft_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    executable_plan_candidate_ref: str = Field(min_length=1)
    expected_dataset_schema_ref: str = Field(min_length=1)
    required_outputs: list[str] = Field(min_length=1)
    expected_language: Literal["python", "spss"] = "python"
    expected_languages: list[Literal["python", "spss"]] = Field(min_length=1)


class ModelDiagnosticRecommendation(AgentContract):
    recommendation_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    model_specification_ref: str = Field(min_length=1)
    diagnostic_checks: list[str] = Field(min_length=1)
    interpretation_limitations: list[str] = Field(default_factory=list)


class RobustnessCheckPlan(AgentContract):
    plan_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    preregistered_plan_ref: str = Field(min_length=1)
    planned_checks: list[str] = Field(min_length=1)
    reporting_rule: str = Field(min_length=1)


class ResultInterpretationBoundary(AgentContract):
    """Permitted interpretation boundary after deterministic result parsing."""

    boundary_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    statistical_result_card_ref: str = Field(min_length=1)
    execution_status: ExecutionStatus
    allowed_interpretations: list[str] = Field(default_factory=list)
    prohibited_interpretations: list[str] = Field(min_length=1)
    requires_human_review: Literal[True] = True


class DataAnalysisPreAnalysisOutcome(AgentContract):
    """Complete, proposal-only package returned by PRE_ANALYSIS."""

    agent_result: "AgentResult"
    readiness_report: AnalysisReadinessReport
    data_audit_specification: DataAuditSpecification
    data_processing_plan_candidate: DataProcessingPlanCandidate
    executable_plan_candidate: ExecutableAnalysisPlanCandidate
    code_specification_draft: CodeSpecificationDraft
    model_diagnostic_recommendation: ModelDiagnosticRecommendation
    robustness_check_plan: RobustnessCheckPlan


class DataAnalysisInterpretationOutcome(AgentContract):
    """Post-execution boundary only; no result values are duplicated here."""

    agent_result: "AgentResult"
    interpretation_boundary: ResultInterpretationBoundary


class DataAnalysisPreAnalysisInput(AgentContract):
    """Controller-supplied PRE_ANALYSIS context, intentionally reference-only."""

    agent_run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    task_ref: str = Field(min_length=1)
    study_protocol_ref: str = Field(min_length=1)
    preregistered_plan_ref: str = Field(min_length=1)
    preregistered_plan_status: Literal["frozen"]
    preregistration_approval_ref: str = Field(min_length=1)
    data_collection_schema_ref: str = Field(min_length=1)
    variable_dictionary_ref: str = Field(min_length=1)
    analysis_mode: AnalysisMode
    model_specification_refs: list[str] = Field(min_length=1)
    required_variables: list[str] = Field(min_length=1)
    missingness_checks: list[str] = Field(min_length=1)
    range_and_type_checks: list[str] = Field(min_length=1)
    privacy_checks: list[str] = Field(min_length=1)
    proposed_processing_steps: list[str] = Field(min_length=1)
    missing_data_strategy_ref: str = Field(min_length=1)
    exclusion_rule_refs: list[str] = Field(default_factory=list)
    diagnostic_checks: list[str] = Field(min_length=1)
    robustness_checks: list[str] = Field(min_length=1)


class DataAnalysisPostExecutionInput(AgentContract):
    """Read-only input for interpretation boundaries after result validation."""

    agent_run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    task_ref: str = Field(min_length=1)
    statistical_result_card_ref: str = Field(min_length=1)
    execution_status: ExecutionStatus
    interpretation_status: Literal["pending_human_review"] = "pending_human_review"

    @model_validator(mode="after")
    def require_verified_result(self) -> "DataAnalysisPostExecutionInput":
        if self.execution_status is ExecutionStatus.GENERATED:
            raise ValueError("interpretation requires a verified statistical result card")
        return self

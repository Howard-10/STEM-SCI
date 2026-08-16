"""Traceable analysis-plan, execution-validation, and result-card contracts.

The contracts in this module deliberately separate preregistration from an
executable plan and separate deterministic result construction from an
Agent's interpretation of a result.  They contain no execution code.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from stem_sci.core.models import DomainModel

from .mode_policy import AnalysisMode


class ExecutionStatus(StrEnum):
    """How far deterministic execution and validation have progressed."""

    GENERATED = "generated"
    EXECUTION_VERIFIED = "execution_verified"
    CROSS_ENGINE_VERIFIED = "cross_engine_verified"


class InterpretationStatus(StrEnum):
    """Human review state for an interpretation; distinct from numeric validity."""

    PENDING_HUMAN_REVIEW = "pending_human_review"
    HUMAN_APPROVED = "human_approved"
    REJECTED = "rejected"


class ValidationMode(StrEnum):
    """Whether results received one-engine or cross-engine validation."""

    SINGLE_ENGINE = "SINGLE_ENGINE"
    CROSS_ENGINE = "CROSS_ENGINE"


class AnalysisModelSpecification(DomainModel):
    """A replaceable model description; it is not restricted to LMM."""

    model_spec_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    model_family: str = Field(min_length=1)
    outcome_variables: list[str] = Field(min_length=1)
    predictor_variables: list[str] = Field(default_factory=list)
    grouping_variables: list[str] = Field(default_factory=list)
    repeated_measure_structure: str | None = None
    formula_or_design: str = Field(min_length=1)
    human_readable_formula: str | None = None
    executable_fixed_formula: str | None = None
    groups_variable: str | None = None
    re_formula: str | None = None
    primary_contrast_weights: dict[str, float] = Field(default_factory=dict)
    reference_levels: dict[str, str] = Field(default_factory=dict)
    inference_contract_ref: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)


class ExecutableAnalysisPlan(DomainModel):
    """Schema-bound compilation of an approved preregistered plan.

    It may map variable names, confirm their types, and select software
    settings.  Substantive choices (outcomes, models, covariates, exclusion
    rules, or missing-data strategy) remain in the preregistered plan or an
    approved amendment.
    """

    executable_plan_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    preregistered_plan_ref: str = Field(min_length=1)
    frozen_dataset_ref: str = Field(min_length=1)
    frozen_dataset_sha256: str = Field(min_length=64, max_length=64)
    dataset_schema_ref: str = Field(min_length=1)
    variable_mapping: dict[str, str] = Field(default_factory=dict)
    type_confirmations: dict[str, str] = Field(default_factory=dict)
    software_configuration: dict[str, str] = Field(default_factory=dict)
    analysis_mode: AnalysisMode
    model_specification_refs: list[str] = Field(min_length=1)
    compatibility_gate_ref: str | None = None


class SubstantiveAnalysisChange(DomainModel):
    """One change that cannot be silently compiled into an executable plan."""

    field: Literal[
        "primary_outcome",
        "model",
        "covariate",
        "exclusion_rule",
        "missing_data_strategy",
    ]
    previous_value: str | None = None
    proposed_value: str = Field(min_length=1)


class AnalysisPlanAmendment(DomainModel):
    """Auditable, human-approved change to a preregistered plan."""

    amendment_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    preregistered_plan_ref: str = Field(min_length=1)
    substantive_changes: list[SubstantiveAnalysisChange] = Field(min_length=1)
    reason: str = Field(min_length=1)
    created_at: datetime
    results_viewed: bool
    analysis_label: Literal["confirmatory", "exploratory"]
    approval_ref: str | None = None
    status: Literal["candidate", "approved", "rejected"] = "candidate"

    @model_validator(mode="after")
    def validate_human_approval(self) -> "AnalysisPlanAmendment":
        if self.status == "approved" and self.approval_ref is None:
            raise ValueError("approved analysis plan amendments require approval_ref")
        if self.status != "approved" and self.approval_ref is not None:
            raise ValueError("only approved analysis plan amendments may have approval_ref")
        if self.results_viewed and self.analysis_label != "exploratory":
            raise ValueError("amendments created after results are viewed must be exploratory")
        return self


class AnalysisPlan(DomainModel):
    plan_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    mode: str = Field(min_length=1)
    primary_outcomes: list[str] = Field(min_length=1)
    model_spec_refs: list[str] = Field(min_length=1)
    status: Literal["candidate", "approved", "frozen"] = "candidate"
    approval_ref: str | None = None
    frozen_at: datetime | None = None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> AnalysisPlan:
        if self.status in {"approved", "frozen"} and not self.approval_ref:
            raise ValueError("approved or frozen analysis plans require approval_ref")
        if self.status == "frozen" and self.frozen_at is None:
            raise ValueError("frozen analysis plans require frozen_at")
        if self.status != "frozen" and self.frozen_at is not None:
            raise ValueError("only frozen analysis plans may have frozen_at")
        return self


class StatisticalResultCard(DomainModel):
    """A card built by a deterministic parser after result validation.

    Agents may read this card, but their candidate outputs must never create or
    alter its values.
    """

    result_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    execution_run_ref: str = Field(min_length=1)
    analysis_plan_ref: str = Field(min_length=1)
    validation_report_ref: str = Field(min_length=1)
    execution_status: ExecutionStatus
    interpretation_status: InterpretationStatus = InterpretationStatus.PENDING_HUMAN_REVIEW
    deterministic_parser_version: str = Field(min_length=1)
    values: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_execution_state(self) -> "StatisticalResultCard":
        if self.execution_status is ExecutionStatus.GENERATED:
            raise ValueError("official result cards require verified execution")
        return self

    @classmethod
    def build_from_validation(
        cls,
        *,
        result_id: str,
        project_id: str,
        execution_run_ref: str,
        analysis_plan_ref: str,
        validation_report: "ResultValidationReport",
        parsed_values: dict[str, float],
        deterministic_parser_version: str,
    ) -> "StatisticalResultCard":
        """Build an official card only from a passing deterministic validation."""

        if validation_report.project_id != project_id:
            raise ValueError("validation report project does not match result card project")
        if not validation_report.passed:
            raise ValueError("cannot build a result card from a failing validation report")
        if execution_run_ref not in validation_report.execution_run_refs:
            raise ValueError("result card execution run is absent from the validation report")
        return cls(
            result_id=result_id,
            project_id=project_id,
            execution_run_ref=execution_run_ref,
            analysis_plan_ref=analysis_plan_ref,
            validation_report_ref=validation_report.ref,
            execution_status=validation_report.execution_status,
            deterministic_parser_version=deterministic_parser_version,
            values=parsed_values,
        )

    @property
    def ref(self) -> str:
        return f"result-card://{self.result_id}"


class ResultValidationReport(DomainModel):
    """Deterministic validation result for one or two execution engines."""

    report_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    analysis_mode: AnalysisMode
    validation_mode: ValidationMode
    execution_run_refs: list[str] = Field(min_length=1)
    input_integrity_passed: bool
    model_integrity_passed: bool
    numeric_output_integrity_passed: bool
    passed: bool
    result_consistency_report_ref: str | None = None
    finding_refs: list[str] = Field(default_factory=list)
    fit_converged: bool | None = None
    optimizer_warning: bool = False
    variance_boundary: bool = False
    rank_deficient: bool = False
    nonfinite_inference: bool = False
    design_matrix_rank: int | None = Field(default=None, ge=0)
    design_columns: list[str] = Field(default_factory=list)
    group_counts: dict[str, int] = Field(default_factory=dict)
    sequence_counts: dict[str, int] = Field(default_factory=dict)
    task_period_row_counts: dict[str, int] = Field(default_factory=dict)
    variance_boundary_policy_version: str | None = None
    variance_boundary_threshold: float | None = Field(default=None, ge=0.0)
    random_intercept_variance: float | None = Field(default=None, ge=0.0)
    residual_variance: float | None = Field(default=None, ge=0.0)
    random_to_residual_variance_ratio: float | None = Field(default=None, ge=0.0)
    diagnostics_ref: str | None = None

    @property
    def ref(self) -> str:
        return f"result-validation://{self.report_id}"

    @model_validator(mode="after")
    def validate_mode_contract(self) -> "ResultValidationReport":
        if self.analysis_mode is AnalysisMode.PYTHON_ONLY:
            if self.validation_mode is not ValidationMode.SINGLE_ENGINE:
                raise ValueError("PYTHON_ONLY requires SINGLE_ENGINE validation")
            if len(self.execution_run_refs) != 1:
                raise ValueError("PYTHON_ONLY validation requires exactly one execution run")
            if self.result_consistency_report_ref is not None:
                raise ValueError("PYTHON_ONLY must not claim a cross-engine consistency report")
        if self.analysis_mode is AnalysisMode.SPSS_PYTHON_DUAL:
            if self.validation_mode is not ValidationMode.CROSS_ENGINE:
                raise ValueError("SPSS_PYTHON_DUAL requires CROSS_ENGINE validation")
            if len(self.execution_run_refs) < 2:
                raise ValueError("dual-engine validation requires both execution runs")
            if self.result_consistency_report_ref is None:
                raise ValueError("dual-engine validation requires a consistency report")
        if self.passed and any(
            [
                self.fit_converged is False,
                self.optimizer_warning,
                self.variance_boundary,
                self.rank_deficient,
                self.nonfinite_inference,
            ]
        ):
            raise ValueError("failed model diagnostics cannot produce a passing validation report")
        return self

    @property
    def execution_status(self) -> ExecutionStatus:
        if not self.passed:
            return ExecutionStatus.GENERATED
        if self.validation_mode is ValidationMode.CROSS_ENGINE:
            return ExecutionStatus.CROSS_ENGINE_VERIFIED
        return ExecutionStatus.EXECUTION_VERIFIED


class ResultConsistencyReport(DomainModel):
    """Comparison record produced only for SPSS/Python dual-engine runs."""

    consistency_report_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    spss_execution_run_ref: str = Field(min_length=1)
    python_execution_run_ref: str = Field(min_length=1)
    compared_result_keys: list[str] = Field(min_length=1)
    passed: bool
    tolerance: float = Field(ge=0.0)
    difference_by_key: dict[str, float] = Field(default_factory=dict)
    finding_codes: list[str] = Field(default_factory=list)

    @property
    def ref(self) -> str:
        return f"result-consistency://{self.consistency_report_id}"


class VarianceBoundaryPolicy(DomainModel):
    policy_version: str = "1.0"
    absolute_threshold: float = Field(default=1e-8, ge=0.0)
    residual_ratio_threshold: float = Field(default=1e-6, ge=0.0)

    def threshold(self, residual_variance: float) -> float:
        return max(self.absolute_threshold, self.residual_ratio_threshold * residual_variance)


class HumanExecutionApproval(DomainModel):
    """Content-addressed human approval for one exact analysis execution package."""

    approval_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    approved_at: datetime
    approved_by: str = Field(min_length=1)
    approval_status: Literal["approved", "rejected"]
    plan_sha256: str = Field(min_length=64, max_length=64)
    code_spec_sha256: str = Field(min_length=64, max_length=64)
    code_artifact_sha256: str = Field(min_length=64, max_length=64)
    code_review_result_sha256: str = Field(min_length=64, max_length=64)
    analysis_dataset_sha256: str = Field(min_length=64, max_length=64)
    environment_spec_sha256: str = Field(min_length=64, max_length=64)
    template_version: str = Field(min_length=1)


class ReproducibilityManifest(DomainModel):
    manifest_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    plan_sha256: str = Field(min_length=64, max_length=64)
    code_spec_sha256: str = Field(min_length=64, max_length=64)
    code_artifact_sha256: str = Field(min_length=64, max_length=64)
    frozen_dataset_sha256: str = Field(min_length=64, max_length=64)
    analysis_dataset_sha256: str = Field(min_length=64, max_length=64)
    result_file_sha256: str = Field(min_length=64, max_length=64)
    python_version: str = Field(min_length=1)
    statsmodels_version: str = Field(min_length=1)
    container_image_digest: str | None = None
    dependency_lock_hash: str = Field(min_length=64, max_length=64)
    template_version: str = Field(min_length=1)
    deterministic_template_sha256: str | None = Field(default=None, min_length=64, max_length=64)

    @property
    def ref(self) -> str:
        return f"reproducibility-manifest://{self.manifest_id}"

"""Phase 1 research-protocol contracts produced as agent candidates."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProtocolModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResearchContract(ProtocolModel):
    contract_id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    population: str | None = None
    context: str | None = None
    intervention: str | None = None
    comparator: str | None = None
    outcomes: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)


class ResearchQuestion(ProtocolModel):
    question_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    population: str = Field(min_length=1)
    intervention: str | None = None
    comparator: str | None = None
    outcomes: list[str] = Field(min_length=1)
    context: str = Field(min_length=1)
    approval_ref: str | None = None


class Hypothesis(ProtocolModel):
    hypothesis_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    outcome_ref: str = Field(min_length=1)


class Estimand(ProtocolModel):
    estimand_id: str = Field(min_length=1)
    population: str = Field(min_length=1)
    treatment: str = Field(min_length=1)
    comparator: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    time: str = Field(min_length=1)
    summary_measure: str = Field(min_length=1)


class PrimaryEstimand(Estimand):
    """The one pre-registered estimand that defines the primary conclusion."""


class OutcomeOperationalDefinition(ProtocolModel):
    outcome_id: str = Field(min_length=1)
    construct_name: str = Field(min_length=1)
    measurement_instrument: str = Field(min_length=1)
    scoring_rule: str = Field(min_length=1)
    available_groups: list[str] = Field(min_length=1)
    available_tasks: list[str] = Field(min_length=1)
    directionality: str = Field(min_length=1)


class PrimaryContrast(ProtocolModel):
    contrast_id: str = Field(min_length=1)
    estimand_ref: str = Field(min_length=1)
    coefficient_weights: dict[str, float] = Field(min_length=1)
    reference_group: str = Field(min_length=1)
    reference_measurement_period: str = Field(min_length=1)
    interpretation: str = Field(min_length=1)


class StatisticalInferenceContract(ProtocolModel):
    contract_id: str = Field(min_length=1)
    library: Literal["statsmodels"] = "statsmodels"
    library_version: str = "0.14.6"
    mixedlm_reml: bool = True
    mixedlm_optimizer: tuple[str, ...] = ("lbfgs",)
    mixedlm_maxiter: int = Field(default=200, ge=1)
    confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)
    alpha: float = Field(default=0.05, gt=0.0, lt=1.0)
    mixedlm_inference: Literal["wald_z_normal"] = "wald_z_normal"
    ancova_cov_type: Literal["HC3"] = "HC3"
    ancova_use_t: Literal[True] = True


class CausalDAGRef(ProtocolModel):
    dag_ref: str = Field(min_length=1)


class StudyProtocol(ProtocolModel):
    protocol_id: str = Field(min_length=1)
    research_question_refs: list[str] = Field(min_length=1)
    hypothesis_refs: list[str] = Field(default_factory=list)
    estimand_ref: str = Field(min_length=1)
    design_type: str = Field(min_length=1)
    sampling_plan_ref: str = Field(min_length=1)
    intervention_protocol_ref: str = Field(min_length=1)
    measurement_plan_ref: str = Field(min_length=1)
    ethics_ref: str = Field(min_length=1)
    approval_ref: str | None = None


class PreregisteredAnalysisPlan(ProtocolModel):
    """Frozen pre-data-collection decisions; executable plans cannot replace it."""

    plan_id: str = Field(min_length=1)
    primary_outcomes: list[str] = Field(min_length=1)
    secondary_outcomes: list[str] = Field(default_factory=list)
    confirmatory_models: list[str] = Field(min_length=1)
    covariates: list[str] = Field(default_factory=list)
    exclusion_rules: list[str] = Field(default_factory=list)
    missing_data_strategy: str = Field(min_length=1)
    outlier_strategy: str = Field(min_length=1)
    alpha: float = Field(gt=0.0, lt=1.0)
    multiple_comparison_strategy: str = Field(min_length=1)
    effect_size_requirements: list[str] = Field(default_factory=list)
    confidence_interval_requirements: list[str] = Field(default_factory=list)
    exploratory_analysis_policy: str = Field(min_length=1)
    primary_estimand_ref: str | None = None
    primary_contrast_ref: str | None = None
    outcome_operational_definition_refs: list[str] = Field(default_factory=list)
    inference_contract_ref: str | None = None
    minimum_group_size: int = Field(default=24, ge=1)
    minimum_group_sequence_size: int = Field(default=12, ge=1)
    contract_version: Literal["legacy", "v1.0"] = "legacy"
    status: Literal["candidate", "approved", "frozen"] = "candidate"
    approval_ref: str | None = None
    frozen_at: datetime | None = None

    @model_validator(mode="after")
    def validate_approval_and_freeze(self) -> PreregisteredAnalysisPlan:
        if self.status in {"approved", "frozen"} and not self.approval_ref:
            raise ValueError("approved or frozen analysis plans require approval_ref")
        if self.status == "frozen" and self.frozen_at is None:
            raise ValueError("frozen analysis plans require frozen_at")
        if self.status != "frozen" and self.frozen_at is not None:
            raise ValueError("only frozen analysis plans may have frozen_at")
        if self.status == "frozen" and self.contract_version == "v1.0":
            required = {
                "primary_estimand_ref": self.primary_estimand_ref,
                "primary_contrast_ref": self.primary_contrast_ref,
                "inference_contract_ref": self.inference_contract_ref,
                "outcome_operational_definition_refs": self.outcome_operational_definition_refs,
            }
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise ValueError("frozen analysis plans require " + ", ".join(missing))
        return self

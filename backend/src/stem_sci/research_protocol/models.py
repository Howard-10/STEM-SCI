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
    status: Literal["candidate", "approved", "frozen"] = "candidate"
    approval_ref: str | None = None
    frozen_at: datetime | None = None

    @model_validator(mode="after")
    def validate_approval_and_freeze(self) -> "PreregisteredAnalysisPlan":
        if self.status in {"approved", "frozen"} and not self.approval_ref:
            raise ValueError("approved or frozen analysis plans require approval_ref")
        if self.status == "frozen" and self.frozen_at is None:
            raise ValueError("frozen analysis plans require frozen_at")
        if self.status != "frozen" and self.frozen_at is not None:
            raise ValueError("only frozen analysis plans may have frozen_at")
        return self

"""Reference-only analysis and result-validation contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from stem_sci.core.models import DomainModel


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
    result_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    execution_run_ref: str = Field(min_length=1)
    analysis_plan_ref: str = Field(min_length=1)
    values: dict[str, float] = Field(default_factory=dict)

    @property
    def ref(self) -> str:
        return f"result-card://{self.result_id}"


class ResultValidationReport(DomainModel):
    report_id: str = Field(min_length=1)
    result_ref: str = Field(min_length=1)
    passed: bool
    finding_refs: list[str] = Field(default_factory=list)

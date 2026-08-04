"""Explicit analysis execution-mode policy contracts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator


class AnalysisMode(StrEnum):
    PYTHON_ONLY = "PYTHON_ONLY"
    SPSS_PYTHON_DUAL = "SPSS_PYTHON_DUAL"


class AnalysisModePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: AnalysisMode
    python_required: bool = True
    spss_required: bool = False

    @model_validator(mode="after")
    def validate_mode_requirements(self) -> AnalysisModePolicy:
        if self.mode is AnalysisMode.PYTHON_ONLY and not self.python_required:
            raise ValueError("PYTHON_ONLY mode requires python_required")
        if self.mode is AnalysisMode.SPSS_PYTHON_DUAL and (
            not self.python_required or not self.spss_required
        ):
            raise ValueError("SPSS_PYTHON_DUAL mode requires Python and SPSS execution")
        return self

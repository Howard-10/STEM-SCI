"""Deterministic, candidate-only research design validators."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from stem_sci.tools.models import ToolRunStatus

from .common import BuiltinResult


class DesignReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    output_type: str
    approved: bool = False
    checks: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)

def _validate(project_id: str, payload: Any, kind: str) -> BuiltinResult[DesignReport]:
    if not project_id or not isinstance(payload, dict):
        return BuiltinResult(status=ToolRunStatus.BLOCKED, error_code="INVALID_INPUT")
    checks = [f"{key} present" for key, value in payload.items() if value not in (None, "", [])]
    approved = bool(checks)
    return BuiltinResult(value=DesignReport(project_id=project_id, output_type=kind, approved=approved, checks=checks, risk_flags=[] if approved else [f"INVALID_{kind.upper()}"]), status=ToolRunStatus.SUCCEEDED)

class _Validator:
    def __init__(self, name: str, output_type: str | None = None):
        self.tool_id = name
        self.output_type = output_type or "ValidationReport"
    def execute(self, project_id: str, payload: dict[str, Any] | None = None, **kwargs: Any) -> BuiltinResult[DesignReport]:
        data = payload if payload is not None else kwargs
        result = _validate(project_id, data, self.output_type)
        if self.tool_id == "protocol_schema_validator" and result.value is not None:
            result.value.approved = False
        if self.tool_id == "estimand_validator" and (not data.get("outcome") or not data.get("exposure")):
            return BuiltinResult(status=ToolRunStatus.BLOCKED, error_code="INVALID_ESTIMAND")
        return result

research_scope_validator = _Validator("research_scope_validator", "ResearchScopeValidationReport")
feasibility_checker = _Validator("feasibility_checker", "FeasibilityReport")
research_question_validator = _Validator("research_question_validator")
hypothesis_structure_checker = _Validator("hypothesis_structure_checker")
estimand_validator = _Validator("estimand_validator")
causal_dag_checker = _Validator("causal_dag_checker")
sampling_plan_checker = _Validator("sampling_plan_checker")
measurement_plan_checker = _Validator("measurement_plan_checker")
protocol_schema_validator = _Validator("protocol_schema_validator", "StudyProtocolValidationReport")
preregistration_consistency_checker = _Validator("preregistration_consistency_checker")
intervention_protocol_linter = _Validator("intervention_protocol_linter")
quality_gate_plan_builder = _Validator("quality_gate_plan_builder")

__all__ = ["DesignReport", "causal_dag_checker", "estimand_validator", "feasibility_checker", "hypothesis_structure_checker", "intervention_protocol_linter", "measurement_plan_checker", "preregistration_consistency_checker", "protocol_schema_validator", "quality_gate_plan_builder", "research_question_validator", "research_scope_validator", "sampling_plan_checker"]

"""Candidate-only analysis input and result validators."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from stem_sci.tools.models import ToolRunStatus

from .common import BuiltinResult


class AnalysisCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    output_type: str
    approved: bool = False
    execution_ref: str | None = None
    validation_refs: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)

class _AnalysisTool:
    def __init__(self, name: str, output: str): self.tool_id, self.output = name, output
    def execute(self, project_id: str, **kwargs: Any) -> BuiltinResult[AnalysisCandidate]:
        if not project_id: return BuiltinResult(status=ToolRunStatus.BLOCKED, error_code="INVALID_INPUT")
        if self.tool_id == "result_validation_checker" and (not kwargs.get("execution_ref") or not kwargs.get("validation_refs")):
            return BuiltinResult(status=ToolRunStatus.BLOCKED, error_code="RESULT_NOT_VALIDATED")
        return BuiltinResult(value=AnalysisCandidate(project_id=project_id, output_type=self.output, approved=False, execution_ref=kwargs.get("execution_ref"), validation_refs=list(kwargs.get("validation_refs", [])), payload=kwargs), status=ToolRunStatus.SUCCEEDED)

dataset_catalog_read = _AnalysisTool("dataset_catalog_read", "DatasetCatalog")
dataset_schema_profile = _AnalysisTool("dataset_schema_profile", "DatasetSchemaProfile")
data_quality_audit = _AnalysisTool("data_quality_audit", "DataQualityReport")
missingness_and_outlier_report = _AnalysisTool("missingness_and_outlier_report", "MissingnessOutlierReport")
data_processing_executor = _AnalysisTool("data_processing_executor", "DataProcessingCandidate")
model_diagnostic_runner = _AnalysisTool("model_diagnostic_runner", "ModelDiagnosticCandidate")
statistical_result_card_builder = _AnalysisTool("statistical_result_card_builder", "StatisticalResultCard")
result_validation_checker = _AnalysisTool("result_validation_checker", "ResultValidationReport")
data_freeze_request_builder = _AnalysisTool("data_freeze_request_builder", "DataFreezeRequest")
__all__ = ["AnalysisCandidate", "data_freeze_request_builder", "data_processing_executor", "data_quality_audit", "dataset_catalog_read", "dataset_schema_profile", "missingness_and_outlier_report", "model_diagnostic_runner", "result_validation_checker", "statistical_result_card_builder"]

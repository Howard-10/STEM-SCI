"""Deterministic SPSS/Python cross-engine result comparison."""

from __future__ import annotations

import math

from stem_sci.core.enums import RunStatus
from stem_sci.core.models import DomainModel
from stem_sci.statistics.mode_policy import AnalysisMode
from stem_sci.statistics.models import (
    ResultConsistencyReport,
    ResultValidationReport,
    ValidationMode,
)
from stem_sci.statistics.python_operator import PythonExecutionOutcome
from stem_sci.statistics.spss_adapter import SpssExecutionOutcome


class DualEngineValidationOutcome(DomainModel):
    consistency_report: ResultConsistencyReport
    validation_report: ResultValidationReport


class CrossEngineResultValidator:
    """Compare normalized values from two independently executed engines."""

    def validate(
        self,
        *,
        report_id: str,
        consistency_report_id: str,
        python_outcome: PythonExecutionOutcome,
        spss_outcome: SpssExecutionOutcome,
        tolerance: float = 1e-7,
    ) -> DualEngineValidationOutcome:
        python_run = python_outcome.execution_run
        spss_run = spss_outcome.execution_run
        finding_codes: list[str] = []
        input_integrity = (
            python_run.status is RunStatus.SUCCEEDED
            and spss_run.status is RunStatus.SUCCEEDED
            and python_run.project_id == spss_run.project_id
            and python_outcome.executable_plan.analysis_mode is AnalysisMode.SPSS_PYTHON_DUAL
            and python_outcome.executable_plan.frozen_dataset_ref == python_outcome.frozen_dataset.ref
            and python_outcome.executable_plan.frozen_dataset_sha256 == python_outcome.frozen_dataset.sha256
        )
        if not input_integrity:
            finding_codes.append("DUAL_INPUT_OR_RUN_INTEGRITY_FAILED")
        model_integrity = (
            python_run.operator_id == "python_analysis"
            and spss_run.operator_id == "spss_analysis"
            and bool(python_outcome.result_values)
            and bool(spss_outcome.result_values)
        )
        if not model_integrity:
            finding_codes.append("DUAL_MODEL_INTEGRITY_FAILED")

        python_keys = set(python_outcome.result_values)
        spss_keys = set(spss_outcome.result_values)
        if python_keys != spss_keys:
            finding_codes.append("DUAL_RESULT_KEY_SET_MISMATCH")
        compared_keys = sorted(python_keys.intersection(spss_keys))
        differences: dict[str, float] = {}
        numeric_integrity = bool(compared_keys)
        for key in compared_keys:
            python_value = python_outcome.result_values[key]
            spss_value = spss_outcome.result_values[key]
            if not math.isfinite(python_value) or not math.isfinite(spss_value):
                numeric_integrity = False
                finding_codes.append("DUAL_NONFINITE_RESULT")
                continue
            difference = abs(python_value - spss_value)
            differences[key] = difference
            if difference > tolerance * max(1.0, abs(python_value), abs(spss_value)):
                numeric_integrity = False
        if not numeric_integrity and "DUAL_NONFINITE_RESULT" not in finding_codes:
            finding_codes.append("DUAL_NUMERIC_MISMATCH")
        passed = input_integrity and model_integrity and numeric_integrity and python_keys == spss_keys
        consistency = ResultConsistencyReport(
            consistency_report_id=consistency_report_id,
            project_id=python_run.project_id,
            spss_execution_run_ref=spss_run.operator_run_id,
            python_execution_run_ref=python_run.operator_run_id,
            compared_result_keys=compared_keys or ["no-comparable-result-keys"],
            passed=passed,
            tolerance=tolerance,
            difference_by_key=differences,
            finding_codes=finding_codes,
        )
        validation = ResultValidationReport(
            report_id=report_id,
            project_id=python_run.project_id,
            analysis_mode=AnalysisMode.SPSS_PYTHON_DUAL,
            validation_mode=ValidationMode.CROSS_ENGINE,
            execution_run_refs=[python_run.operator_run_id, spss_run.operator_run_id],
            input_integrity_passed=input_integrity,
            model_integrity_passed=model_integrity,
            numeric_output_integrity_passed=numeric_integrity,
            passed=passed,
            result_consistency_report_ref=consistency.ref,
            finding_refs=[f"finding://cross-engine/{code.lower()}" for code in finding_codes],
        )
        return DualEngineValidationOutcome(
            consistency_report=consistency, validation_report=validation
        )

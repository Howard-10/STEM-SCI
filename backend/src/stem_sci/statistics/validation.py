"""Deterministic result validation for the single-engine MVP."""

from __future__ import annotations

import math

from stem_sci.core.enums import RunStatus
from stem_sci.research_data.freeze import DataFreezeService, FrozenDatasetIntegrityError
from stem_sci.statistics.mode_policy import AnalysisMode
from stem_sci.statistics.models import ResultValidationReport, ValidationMode
from stem_sci.statistics.python_operator import PythonExecutionOutcome


class SingleEngineResultValidator:
    """Validate frozen-input, model, numeric-output, and run provenance."""

    def __init__(self, *, freeze_service: DataFreezeService | None = None) -> None:
        self.freeze_service = freeze_service or DataFreezeService()

    def validate(
        self, outcome: PythonExecutionOutcome, report_id: str
    ) -> ResultValidationReport:
        run = outcome.execution_run
        input_integrity_passed = run.status is RunStatus.SUCCEEDED and bool(run.input_artifact_refs)
        if input_integrity_passed:
            try:
                self.freeze_service.assert_integrity(outcome.frozen_dataset)
            except FrozenDatasetIntegrityError:
                input_integrity_passed = False
        model_integrity_passed = (
            run.status is RunStatus.SUCCEEDED
            and run.operator_id == "python_analysis"
            and outcome.executable_plan.analysis_mode is AnalysisMode.PYTHON_ONLY
            and outcome.executable_plan.frozen_dataset_ref == outcome.frozen_dataset.ref
            and outcome.executable_plan.frozen_dataset_sha256 == outcome.frozen_dataset.sha256
        )
        numeric_output_integrity_passed = bool(outcome.result_values) and all(
            math.isfinite(value) for value in outcome.result_values.values()
        )
        passed = (
            input_integrity_passed and model_integrity_passed and numeric_output_integrity_passed
        )
        findings = [] if passed else ["finding://single-engine-validation/failed"]
        return ResultValidationReport(
            report_id=report_id,
            project_id=run.project_id,
            analysis_mode=AnalysisMode.PYTHON_ONLY,
            validation_mode=ValidationMode.SINGLE_ENGINE,
            execution_run_refs=[run.operator_run_id],
            input_integrity_passed=input_integrity_passed,
            model_integrity_passed=model_integrity_passed,
            numeric_output_integrity_passed=numeric_output_integrity_passed,
            passed=passed,
            finding_refs=findings,
        )

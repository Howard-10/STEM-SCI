"""Deterministic CSV/PYTHON_ONLY analysis operator used by the MVP.

This is an Operator implementation, not an Agent.  It reads only a validated
FrozenDataset, writes only an execution-run directory, and records every run.
"""

from __future__ import annotations

import csv
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import Field

from stem_sci.artifacts.execution_store import ExecutionStore, InMemoryExecutionStore
from stem_sci.core.enums import RunStatus
from stem_sci.core.models import DomainModel
from stem_sci.operators.models import OperatorRun
from stem_sci.research_data.freeze import DataFreezeService, FrozenDatasetIntegrityError
from stem_sci.research_data.models import FrozenDatasetRef
from stem_sci.statistics.mode_policy import AnalysisMode
from stem_sci.statistics.models import AnalysisModelSpecification, ExecutableAnalysisPlan
from stem_sci.utils.hash_utils import sha256_bytes, sha256_text


class PythonAnalysisRequest(DomainModel):
    """Controller-approved input for the narrow PYTHON_ONLY MVP operator."""

    project_id: str = Field(min_length=1)
    frozen_dataset: FrozenDatasetRef
    executable_plan: ExecutableAnalysisPlan
    model_specification: AnalysisModelSpecification
    code_artifact_ref: str = Field(min_length=1)


class PythonExecutionOutcome(DomainModel):
    """Execution provenance plus values parsed from a stable JSON artifact."""

    execution_run: OperatorRun
    frozen_dataset: FrozenDatasetRef
    executable_plan: ExecutableAnalysisPlan
    model_specification: AnalysisModelSpecification
    result_values: dict[str, float] = Field(default_factory=dict)
    result_payload_sha256: str | None = None


class CsvPythonAnalysisOperator:
    """Run a transparent two-group mean-difference analysis on a frozen CSV.

    The MVP supports ``group_mean_difference`` only.  The surrounding contract
    uses ``AnalysisModelSpecification`` so later operators can add LMM or other
    model families without changing the workflow model.
    """

    operator_id = "python_analysis"
    operator_version = "mvp-csv-v1"
    supported_model_family = "group_mean_difference"

    def __init__(
        self,
        *,
        freeze_service: DataFreezeService | None = None,
        execution_store: ExecutionStore | None = None,
    ) -> None:
        self.freeze_service = freeze_service or DataFreezeService()
        self.execution_store = execution_store or InMemoryExecutionStore()

    def execute(self, request: PythonAnalysisRequest, output_root: Path) -> PythonExecutionOutcome:
        run_id = f"execution-{uuid4().hex}"
        now = datetime.now(UTC)
        try:
            self._validate_request(request)
            self.freeze_service.assert_integrity(request.frozen_dataset)
        except (FrozenDatasetIntegrityError, ValueError) as exc:
            run = OperatorRun(
                operator_run_id=run_id,
                project_id=request.project_id,
                operator_id=self.operator_id,
                operator_version=self.operator_version,
                request_ref=request.code_artifact_ref,
                input_artifact_refs=[
                    request.frozen_dataset.ref,
                    f"executable-plan://{request.executable_plan.executable_plan_id}",
                    f"model-spec://{request.model_specification.model_spec_id}",
                ],
                log_ref=f"log://{run_id}",
                error_ref=(
                    "error://frozen-dataset-integrity"
                    if isinstance(exc, FrozenDatasetIntegrityError)
                    else "error://python-analysis-input"
                ),
                status=RunStatus.BLOCKED,
                started_at=now,
                finished_at=datetime.now(UTC),
            )
            return PythonExecutionOutcome(
                execution_run=self.execution_store.put(run),
                frozen_dataset=request.frozen_dataset,
                executable_plan=request.executable_plan,
                model_specification=request.model_specification,
            )

        try:
            values = self._calculate_group_mean_difference(request.frozen_dataset)
            run_directory = output_root / sha256_text(request.project_id)[:16] / run_id
            run_directory.mkdir(parents=True, exist_ok=False)
            payload = {
                "parser_version": "python-result-parser-v1",
                "model_family": request.model_specification.model_family,
                "values": values,
            }
            output_path = run_directory / "result.json"
            payload_bytes = json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            output_path.write_bytes(payload_bytes)
            run = OperatorRun(
                operator_run_id=run_id,
                project_id=request.project_id,
                operator_id=self.operator_id,
                operator_version=self.operator_version,
                request_ref=request.code_artifact_ref,
                input_artifact_refs=[
                    request.frozen_dataset.ref,
                    f"executable-plan://{request.executable_plan.executable_plan_id}",
                    f"model-spec://{request.model_specification.model_spec_id}",
                ],
                output_artifact_refs=[f"execution-output://{run_id}"],
                environment_ref="environment://python-only/mvp-csv-v1",
                log_ref=f"log://{run_id}",
                status=RunStatus.SUCCEEDED,
                started_at=now,
                finished_at=datetime.now(UTC),
            )
            return PythonExecutionOutcome(
                execution_run=self.execution_store.put(run),
                frozen_dataset=request.frozen_dataset,
                executable_plan=request.executable_plan,
                model_specification=request.model_specification,
                result_values=values,
                result_payload_sha256=sha256_bytes(payload_bytes),
            )
        except (OSError, UnicodeDecodeError, csv.Error, ValueError):
            run = OperatorRun(
                operator_run_id=run_id,
                project_id=request.project_id,
                operator_id=self.operator_id,
                operator_version=self.operator_version,
                request_ref=request.code_artifact_ref,
                input_artifact_refs=[request.frozen_dataset.ref],
                log_ref=f"log://{run_id}",
                error_ref="error://python-analysis-execution",
                status=RunStatus.FAILED,
                started_at=now,
                finished_at=datetime.now(UTC),
            )
            return PythonExecutionOutcome(
                execution_run=self.execution_store.put(run),
                frozen_dataset=request.frozen_dataset,
                executable_plan=request.executable_plan,
                model_specification=request.model_specification,
            )

    def _validate_request(self, request: PythonAnalysisRequest) -> None:
        if request.executable_plan.project_id != request.project_id:
            raise ValueError("executable plan project does not match execution project")
        if request.frozen_dataset.project_id != request.project_id:
            raise ValueError("frozen dataset project does not match execution project")
        if request.model_specification.project_id != request.project_id:
            raise ValueError("model specification project does not match execution project")
        if request.executable_plan.analysis_mode is not AnalysisMode.PYTHON_ONLY:
            raise ValueError("MVP Python operator accepts PYTHON_ONLY plans only")
        if request.executable_plan.frozen_dataset_ref != request.frozen_dataset.ref:
            raise ValueError("executable plan references a different frozen dataset")
        if request.executable_plan.frozen_dataset_sha256 != request.frozen_dataset.sha256:
            raise ValueError("executable plan frozen-dataset hash does not match")
        if request.model_specification.model_family != self.supported_model_family:
            raise ValueError("MVP Python operator does not support the requested model family")

    @staticmethod
    def _calculate_group_mean_difference(dataset: FrozenDatasetRef) -> dict[str, float]:
        groups: dict[str, list[float]] = {}
        with Path(dataset.content_uri).open("r", encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            required = {"group", "transfer_score"}
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise ValueError("CSV must include group and transfer_score columns")
            for row in reader:
                group = (row.get("group") or "").strip()
                if not group:
                    raise ValueError("group values must be non-empty")
                try:
                    score = float(row.get("transfer_score") or "")
                except ValueError as exc:
                    raise ValueError("transfer_score values must be numeric") from exc
                if not math.isfinite(score):
                    raise ValueError("transfer_score values must be finite")
                groups.setdefault(group, []).append(score)
        if len(groups) != 2:
            raise ValueError("MVP group_mean_difference requires exactly two groups")
        ordered_groups = sorted(groups)
        first_group, second_group = ordered_groups
        first_mean = sum(groups[first_group]) / len(groups[first_group])
        second_mean = sum(groups[second_group]) / len(groups[second_group])
        values = {
            "group_1_n": float(len(groups[first_group])),
            "group_1_transfer_mean": first_mean,
            "group_2_n": float(len(groups[second_group])),
            "group_2_transfer_mean": second_mean,
            "transfer_mean_difference_group_2_minus_group_1": second_mean - first_mean,
        }
        if not all(math.isfinite(value) for value in values.values()):
            raise ValueError("calculated values must be finite")
        return values

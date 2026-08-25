"""Fail-closed IBM SPSS adapter for future dual-engine verification.

The adapter is intentionally honest about local capability: without an
installed, explicitly configured SPSS batch executable it produces a blocked
run.  It never silently falls back to Python while retaining a dual-engine
label.
"""

from __future__ import annotations

import csv
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import Field

from stem_sci.coding.models import CodeArtifact
from stem_sci.core.enums import RunStatus
from stem_sci.core.models import DomainModel
from stem_sci.operators.models import OperatorRun
from stem_sci.research_data.freeze import DataFreezeService, FrozenDatasetIntegrityError
from stem_sci.research_data.models import FrozenDatasetRef
from stem_sci.statistics.mode_policy import AnalysisMode
from stem_sci.statistics.models import AnalysisModelSpecification, ExecutableAnalysisPlan
from stem_sci.utils.hash_utils import sha256_text


class SpssAvailability(DomainModel):
    available: bool
    executable_path: str | None = None
    reason_code: str | None = None


class SpssAnalysisRequest(DomainModel):
    project_id: str = Field(min_length=1)
    frozen_dataset: FrozenDatasetRef
    executable_plan: ExecutableAnalysisPlan
    model_specification: AnalysisModelSpecification
    syntax_artifact: CodeArtifact
    syntax_review_ref: str = Field(min_length=1)


class SpssExecutionOutcome(DomainModel):
    execution_run: OperatorRun
    result_values: dict[str, float] = Field(default_factory=dict)
    result_payload_ref: str | None = None


class SpssAdapter:
    """Execute reviewed SPSS syntax only when a batch runtime is available."""

    operator_id = "spss_analysis"
    operator_version = "spss-adapter-v1"

    def __init__(
        self,
        *,
        executable: Path | None = None,
        freeze_service: DataFreezeService | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        self.executable = executable
        self.freeze_service = freeze_service or DataFreezeService()
        self.timeout_seconds = timeout_seconds

    def detect(self) -> SpssAvailability:
        candidate = self.executable or self._configured_executable()
        if candidate is None:
            return SpssAvailability(available=False, reason_code="SPSS_EXECUTABLE_NOT_FOUND")
        if not candidate.is_file():
            return SpssAvailability(available=False, reason_code="SPSS_EXECUTABLE_NOT_FOUND")
        return SpssAvailability(available=True, executable_path=str(candidate))

    def execute(self, request: SpssAnalysisRequest, output_root: Path) -> SpssExecutionOutcome:
        run_id = f"execution-{uuid4().hex}"
        now = datetime.now(UTC)
        preflight_error = self._preflight_error(request)
        if preflight_error is not None:
            return SpssExecutionOutcome(
                execution_run=self._run(
                    run_id, request, RunStatus.BLOCKED, now, error_ref=f"error://spss/{preflight_error}"
                )
            )
        availability = self.detect()
        if not availability.available or availability.executable_path is None:
            return SpssExecutionOutcome(
                execution_run=self._run(
                    run_id,
                    request,
                    RunStatus.BLOCKED,
                    now,
                    error_ref=f"error://spss/{availability.reason_code or 'unavailable'}",
                )
            )
        run_directory = output_root / sha256_text(request.project_id)[:16] / run_id
        run_directory.mkdir(parents=True, exist_ok=False)
        result_csv = run_directory / "spss_aggregate.csv"
        syntax_path = run_directory / "analysis.sps"
        log_path = run_directory / "spss.log"
        try:
            syntax = Path(request.syntax_artifact.content_uri).read_text(encoding="utf-8")
            syntax_path.write_text(
                self._materialize_syntax(syntax, request.frozen_dataset.content_uri, result_csv),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [availability.executable_path, "-production", "silent", "-f", str(syntax_path)],
                cwd=run_directory,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, UnicodeDecodeError, ValueError, subprocess.TimeoutExpired):
            log_path.write_text("SPSS execution could not be started or completed.\n", encoding="utf-8")
            return SpssExecutionOutcome(
                execution_run=self._run(
                    run_id,
                    request,
                    RunStatus.FAILED,
                    now,
                    log_ref=f"log://{run_id}",
                    error_ref="error://spss/execution-failed",
                )
            )
        log_path.write_text(f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}\n", encoding="utf-8")
        if completed.returncode != 0:
            return SpssExecutionOutcome(
                execution_run=self._run(
                    run_id,
                    request,
                    RunStatus.FAILED,
                    now,
                    log_ref=f"log://{run_id}",
                    error_ref="error://spss/nonzero-exit",
                )
            )
        try:
            values = self._parse_aggregate_output(result_csv)
        except (OSError, UnicodeDecodeError, csv.Error, ValueError):
            return SpssExecutionOutcome(
                execution_run=self._run(
                    run_id,
                    request,
                    RunStatus.FAILED,
                    now,
                    log_ref=f"log://{run_id}",
                    error_ref="error://spss/result-output-invalid",
                )
            )
        return SpssExecutionOutcome(
            execution_run=self._run(
                run_id,
                request,
                RunStatus.SUCCEEDED,
                now,
                log_ref=f"log://{run_id}",
                output_refs=[f"execution-output://{run_id}"],
            ),
            result_values=values,
            result_payload_ref=f"execution-output://{run_id}",
        )

    def _preflight_error(self, request: SpssAnalysisRequest) -> str | None:
        if request.executable_plan.analysis_mode is not AnalysisMode.SPSS_PYTHON_DUAL:
            return "dual-mode-required"
        if request.frozen_dataset.project_id != request.project_id:
            return "project-scope-mismatch"
        if request.executable_plan.project_id != request.project_id:
            return "plan-project-mismatch"
        if request.model_specification.project_id != request.project_id:
            return "model-project-mismatch"
        if request.executable_plan.frozen_dataset_ref != request.frozen_dataset.ref:
            return "frozen-dataset-reference-mismatch"
        if request.executable_plan.frozen_dataset_sha256 != request.frozen_dataset.sha256:
            return "frozen-dataset-hash-mismatch"
        if request.syntax_artifact.language.lower() != "spss":
            return "spss-syntax-required"
        try:
            self.freeze_service.assert_integrity(request.frozen_dataset)
        except FrozenDatasetIntegrityError:
            return "frozen-dataset-integrity-failed"
        return None

    def _run(
        self,
        run_id: str,
        request: SpssAnalysisRequest,
        status: RunStatus,
        started_at: datetime,
        *,
        log_ref: str | None = None,
        error_ref: str | None = None,
        output_refs: list[str] | None = None,
    ) -> OperatorRun:
        return OperatorRun(
            operator_run_id=run_id,
            project_id=request.project_id,
            operator_id=self.operator_id,
            operator_version=self.operator_version,
            request_ref=request.syntax_artifact.ref,
            input_artifact_refs=[
                request.frozen_dataset.ref,
                f"executable-plan://{request.executable_plan.executable_plan_id}",
                request.syntax_artifact.ref,
                request.syntax_review_ref,
            ],
            output_artifact_refs=output_refs or [],
            environment_ref="environment://spss/batch-v1",
            log_ref=log_ref,
            error_ref=error_ref,
            status=status,
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )

    @staticmethod
    def _configured_executable() -> Path | None:
        configured = os.environ.get("STEM_SCI_SPSS_EXECUTABLE")
        if configured:
            return Path(os.path.expandvars(configured.strip().strip('"')))
        command = shutil.which("stats")
        if command:
            return Path(command)
        for ibm_root in (Path("C:/Program Files/IBM"), Path("C:/Program Files (x86)/IBM")):
            if not ibm_root.is_dir():
                continue
            candidates = sorted(
                (candidate for candidate in ibm_root.glob("SPSS*/**/stats.exe") if candidate.is_file()),
                reverse=True,
            )
            if candidates:
                return candidates[0]
        return None

    @staticmethod
    def _materialize_syntax(template: str, dataset_path: str, result_path: Path) -> str:
        if "{{FROZEN_DATASET_PATH}}" not in template or "{{RESULT_CSV_PATH}}" not in template:
            raise ValueError("SPSS syntax must contain controlled data and result placeholders")
        safe_dataset = dataset_path.replace("\"", "\"\"")
        safe_result = str(result_path).replace("\"", "\"\"")
        return template.replace("{{FROZEN_DATASET_PATH}}", safe_dataset).replace(
            "{{RESULT_CSV_PATH}}", safe_result
        )

    @staticmethod
    def _parse_aggregate_output(result_csv: Path) -> dict[str, float]:
        with result_csv.open("r", encoding="utf-8", newline="") as source:
            rows = list(csv.DictReader(source))
        if len(rows) != 2:
            raise ValueError("SPSS aggregate output must contain exactly two groups")
        ordered = sorted(rows, key=lambda row: (row.get("group") or ""))
        first, second = ordered
        first_n, second_n = float(first["n"]), float(second["n"])
        first_mean, second_mean = float(first["mean"]), float(second["mean"])
        first_sd, second_sd = float(first["sd"]), float(second["sd"])
        return {
            "analysis_sample_size": first_n + second_n,
            "group_1_n": first_n,
            "group_1_transfer_mean": first_mean,
            "group_1_transfer_sd": first_sd,
            "group_2_n": second_n,
            "group_2_transfer_mean": second_mean,
            "group_2_transfer_sd": second_sd,
            "transfer_mean_difference_group_2_minus_group_1": second_mean - first_mean,
        }

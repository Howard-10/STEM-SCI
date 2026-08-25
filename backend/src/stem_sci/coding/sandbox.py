"""Narrow local research-code sandbox used by the execution MVP.

This is deliberately a development sandbox, not a claim of production-grade
OS isolation.  It combines a reviewed allow-list, read-only frozen input,
minimal environment, no-network import policy, a fixed working directory and
a hard wall-clock timeout.  A future container runner may satisfy the same
contract with stronger CPU/memory and filesystem isolation.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field

from stem_sci.coding.models import CodeArtifact, CodeSpecification
from stem_sci.coding.review import CodeReviewResult
from stem_sci.core.enums import RunStatus
from stem_sci.core.models import DomainModel
from stem_sci.operators.models import OperatorRun
from stem_sci.research_data.freeze import DataFreezeService, FrozenDatasetIntegrityError
from stem_sci.research_data.models import FrozenDatasetRef
from stem_sci.utils.hash_utils import sha256_bytes, sha256_text


SecurityPosture = Literal["development_restricted"]


class SandboxPolicy(DomainModel):
    policy_id: str = "research-code-v1"
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    maximum_output_bytes: int = Field(default=1_000_000, ge=1, le=5_000_000)
    network_allowed: bool = False
    dependency_installation_allowed: bool = False
    host_filesystem_isolation: SecurityPosture = "development_restricted"


class SandboxExecutionOutcome(DomainModel):
    execution_run: OperatorRun
    result_values: dict[str, float] = Field(default_factory=dict)
    result_payload_sha256: str | None = None
    result_output_ref: str | None = None
    security_posture: str = "development_restricted"
    warning_codes: list[str] = Field(default_factory=list)


class ResearchCodeSandbox:
    """Execute a reviewed Python artifact against exactly one frozen CSV."""

    operator_id = "python_analysis"
    operator_version = "research-sandbox-v1"

    def __init__(
        self,
        *,
        freeze_service: DataFreezeService | None = None,
        policy: SandboxPolicy | None = None,
    ) -> None:
        self.freeze_service = freeze_service or DataFreezeService()
        self.policy = policy or SandboxPolicy()

    def execute(
        self,
        *,
        project_id: str,
        frozen_dataset: FrozenDatasetRef,
        specification: CodeSpecification,
        artifact: CodeArtifact,
        review: CodeReviewResult,
        output_root: Path,
        human_approval_ref: str | None = None,
    ) -> SandboxExecutionOutcome:
        run_id = f"execution-{uuid4().hex}"
        now = datetime.now(UTC)
        block_reason = self._preflight_reason(
            project_id=project_id,
            frozen_dataset=frozen_dataset,
            specification=specification,
            artifact=artifact,
            review=review,
            human_approval_ref=human_approval_ref,
        )
        if block_reason is not None:
            return SandboxExecutionOutcome(
                execution_run=self._run(
                    run_id=run_id,
                    project_id=project_id,
                    request_ref=artifact.ref,
                    input_refs=[frozen_dataset.ref, specification.ref, artifact.ref, review.ref],
                    status=RunStatus.BLOCKED,
                    started_at=now,
                    finished_at=datetime.now(UTC),
                    error_ref=f"error://research-code-sandbox/{block_reason.lower()}",
                ),
                warning_codes=[block_reason],
            )

        run_directory = output_root / sha256_text(project_id)[:16] / run_id
        run_directory.mkdir(parents=True, exist_ok=False)
        code_path = run_directory / specification.entrypoint
        shutil.copyfile(artifact.content_uri, code_path)
        result_path = run_directory / "result.json"
        log_path = run_directory / "execution.log"
        env = self._minimal_environment(run_directory)
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(code_path.resolve()),
                    str(Path(frozen_dataset.content_uri).resolve()),
                    str(result_path.resolve()),
                ],
                cwd=run_directory,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.policy.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            log_path.write_text("execution timed out\n", encoding="utf-8")
            return SandboxExecutionOutcome(
                execution_run=self._run(
                    run_id=run_id,
                    project_id=project_id,
                    request_ref=artifact.ref,
                    input_refs=[frozen_dataset.ref, specification.ref, artifact.ref, review.ref],
                    status=RunStatus.TERMINATED,
                    started_at=now,
                    finished_at=datetime.now(UTC),
                    log_ref=f"log://{run_id}",
                    error_ref="error://research-code-sandbox/timeout",
                ),
                warning_codes=["SANDBOX_TIMEOUT"],
            )
        log_path.write_text(
            self._safe_log(completed.stdout, completed.stderr), encoding="utf-8"
        )
        if completed.returncode != 0:
            return SandboxExecutionOutcome(
                execution_run=self._run(
                    run_id=run_id,
                    project_id=project_id,
                    request_ref=artifact.ref,
                    input_refs=[frozen_dataset.ref, specification.ref, artifact.ref, review.ref],
                    status=RunStatus.FAILED,
                    started_at=now,
                    finished_at=datetime.now(UTC),
                    log_ref=f"log://{run_id}",
                    error_ref="error://research-code-sandbox/analysis-failed",
                ),
                warning_codes=["SANDBOX_ANALYSIS_FAILED"],
            )
        try:
            values, payload_hash = self._parse_result(result_path, frozen_dataset)
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
            return SandboxExecutionOutcome(
                execution_run=self._run(
                    run_id=run_id,
                    project_id=project_id,
                    request_ref=artifact.ref,
                    input_refs=[frozen_dataset.ref, specification.ref, artifact.ref, review.ref],
                    status=RunStatus.FAILED,
                    started_at=now,
                    finished_at=datetime.now(UTC),
                    log_ref=f"log://{run_id}",
                    error_ref="error://research-code-sandbox/invalid-result-output",
                ),
                warning_codes=["SANDBOX_RESULT_INVALID"],
            )
        return SandboxExecutionOutcome(
            execution_run=self._run(
                run_id=run_id,
                project_id=project_id,
                request_ref=artifact.ref,
                input_refs=[frozen_dataset.ref, specification.ref, artifact.ref, review.ref],
                output_refs=[f"execution-output://{run_id}"],
                status=RunStatus.SUCCEEDED,
                started_at=now,
                finished_at=datetime.now(UTC),
                environment_ref="environment://research-code-sandbox/development-restricted-v1",
                log_ref=f"log://{run_id}",
            ),
            result_values=values,
            result_payload_sha256=payload_hash,
            result_output_ref=f"execution-output://{run_id}",
            warning_codes=["DEVELOPMENT_SANDBOX_NO_OS_RESOURCE_LIMITS"],
        )

    def _preflight_reason(
        self,
        *,
        project_id: str,
        frozen_dataset: FrozenDatasetRef,
        specification: CodeSpecification,
        artifact: CodeArtifact,
        review: CodeReviewResult,
        human_approval_ref: str | None,
    ) -> str | None:
        if specification.project_id != project_id or artifact.project_id != project_id:
            return "PROJECT_SCOPE_MISMATCH"
        if specification.frozen_dataset_ref != frozen_dataset.ref:
            return "FROZEN_DATASET_REFERENCE_MISMATCH"
        if specification.frozen_dataset_sha256 != frozen_dataset.sha256:
            return "FROZEN_DATASET_HASH_MISMATCH"
        if not review.passed:
            return "CODE_REVIEW_FAILED"
        if review.requires_human_approval and not human_approval_ref:
            return "CODE_REVIEW_HUMAN_APPROVAL_REQUIRED"
        try:
            self.freeze_service.assert_integrity(frozen_dataset)
        except FrozenDatasetIntegrityError:
            return "FROZEN_DATASET_INTEGRITY_FAILED"
        return None

    def _parse_result(
        self, result_path: Path, frozen_dataset: FrozenDatasetRef
    ) -> tuple[dict[str, float], str]:
        payload_bytes = result_path.read_bytes()
        if len(payload_bytes) > self.policy.maximum_output_bytes:
            raise ValueError("result output exceeds sandbox limit")
        payload = json.loads(payload_bytes.decode("utf-8"))
        if payload.get("parser_version") != "research-python-result-v1":
            raise ValueError("unrecognized result payload version")
        if payload.get("frozen_dataset_sha256") != frozen_dataset.sha256:
            raise ValueError("result payload is not bound to the frozen data hash")
        raw_values = payload.get("values")
        if not isinstance(raw_values, dict) or not raw_values:
            raise ValueError("result payload requires values")
        values: dict[str, float] = {}
        for key, value in raw_values.items():
            if not isinstance(key, str) or not isinstance(value, (float, int)):
                raise ValueError("result payload values must be numeric")
            numeric = float(value)
            if not math.isfinite(numeric):
                raise ValueError("result payload values must be finite")
            values[key] = numeric
        return values, sha256_bytes(payload_bytes)

    def _run(
        self,
        *,
        run_id: str,
        project_id: str,
        request_ref: str,
        input_refs: list[str],
        status: RunStatus,
        started_at: datetime,
        finished_at: datetime,
        output_refs: list[str] | None = None,
        environment_ref: str | None = None,
        log_ref: str | None = None,
        error_ref: str | None = None,
    ) -> OperatorRun:
        return OperatorRun(
            operator_run_id=run_id,
            project_id=project_id,
            operator_id=self.operator_id,
            operator_version=self.operator_version,
            request_ref=request_ref,
            input_artifact_refs=input_refs,
            output_artifact_refs=output_refs or [],
            environment_ref=environment_ref,
            log_ref=log_ref,
            error_ref=error_ref,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
        )

    @staticmethod
    def _minimal_environment(run_directory: Path) -> dict[str, str]:
        environment = {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONNOUSERSITE": "1",
            "PYTHONUTF8": "1",
            "TEMP": str(run_directory),
            "TMP": str(run_directory),
        }
        for key in ("SYSTEMROOT", "WINDIR"):
            value = os.environ.get(key)
            if value:
                environment[key] = value
        return environment

    @staticmethod
    def _safe_log(stdout: str, stderr: str) -> str:
        """Keep only process text; public APIs expose a stable error ref, not it."""

        return f"stdout:\n{stdout}\nstderr:\n{stderr}\n"

"""Deterministic v1.0 statsmodels executors for the frozen STEM-SCI demo."""

from __future__ import annotations

import importlib.metadata
import json
import math
import platform
import warnings
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd  # type: ignore[import-untyped]
import statsmodels.api as sm  # type: ignore[import-untyped]
from pydantic import Field
from scipy.stats import norm  # type: ignore[import-untyped]
from statsmodels.regression.mixed_linear_model import MixedLMResults  # type: ignore[import-untyped]
from statsmodels.tools.sm_exceptions import ConvergenceWarning  # type: ignore[import-untyped]
from numpy.typing import NDArray

from stem_sci.coding.models import CodeArtifact, CodeSpecification
from stem_sci.coding.review import CodeReviewResult
from stem_sci.core.enums import RunStatus
from stem_sci.core.models import DomainModel
from stem_sci.operators.models import OperatorRun
from stem_sci.research_data.models import AnalysisDatasetRef, FrozenDatasetRef
from stem_sci.research_data.canonical import canonical_csv_bytes, read_csv_rows
from stem_sci.research_data.freeze import DataFreezeService, FrozenDatasetIntegrityError
from stem_sci.statistics.models import (
    AnalysisModelSpecification,
    ExecutableAnalysisPlan,
    HumanExecutionApproval,
    ReproducibilityManifest,
    ResultValidationReport,
    ValidationMode,
    VarianceBoundaryPolicy,
)
from stem_sci.statistics.mode_policy import AnalysisMode
from stem_sci.utils.hash_utils import sha256_bytes, sha256_text


class V1ExecutionRequest(DomainModel):
    project_id: str
    frozen_dataset: FrozenDatasetRef
    analysis_dataset: AnalysisDatasetRef
    executable_plan: ExecutableAnalysisPlan
    executable_plan_ref: str
    executable_plan_sha256: str = Field(min_length=64, max_length=64)
    model_specification: AnalysisModelSpecification
    code_specification: CodeSpecification
    code_artifact: CodeArtifact
    code_review: CodeReviewResult
    human_execution_approval: HumanExecutionApproval
    environment_spec_sha256: str = Field(min_length=64, max_length=64)


class V1ExecutionOutcome(DomainModel):
    execution_run: OperatorRun
    result_values: dict[str, float] = Field(default_factory=dict)
    result_payload_sha256: str | None = None
    result_output_ref: str | None = None
    validation_report: ResultValidationReport | None = None
    reproducibility_manifest: ReproducibilityManifest | None = None


@dataclass(frozen=True)
class _FitDiagnostics:
    converged: bool
    optimizer_warning: bool
    variance_boundary: bool
    rank_deficient: bool
    nonfinite_inference: bool
    design_matrix_rank: int
    design_columns: list[str]
    group_counts: dict[str, int]
    sequence_counts: dict[str, int]
    task_period_row_counts: dict[str, int]
    random_intercept_variance: float | None = None
    residual_variance: float | None = None


class DeterministicStatsmodelsExecutor:
    """Execute only approved LMM/ANCOVA templates against an AnalysisDataset."""

    operator_id = "statsmodels_analysis"
    operator_version = "v1.0"
    template_version = "statsmodels-v1.0"
    _model_dataset = {
        "linear_mixed_effects_primary": "primary_lmm",
        "linear_mixed_effects_prompt_dependency": "prompt_dependency_lmm",
        "ols_ancova_transfer": "transfer_ancova",
    }

    def __init__(self, policy: VarianceBoundaryPolicy | None = None) -> None:
        self.policy = policy or VarianceBoundaryPolicy()
        self.freeze_service = DataFreezeService()

    def execute(self, request: V1ExecutionRequest, output_root: Path) -> V1ExecutionOutcome:
        run_id = f"execution-{uuid4().hex}"
        now = datetime.now(UTC)
        preflight = self._preflight(request)
        if preflight is not None:
            return self._not_started(run_id, request, now, preflight)
        try:
            frame = pd.read_csv(request.analysis_dataset.content_uri)
            if request.model_specification.model_family == "linear_mixed_effects_primary":
                values, diagnostics = self._fit_primary_lmm(frame, request.model_specification)
            elif request.model_specification.model_family == "linear_mixed_effects_prompt_dependency":
                values, diagnostics = self._fit_prompt_lmm(frame, request.model_specification)
            elif request.model_specification.model_family == "ols_ancova_transfer":
                values, diagnostics = self._fit_transfer_ancova(frame, request.model_specification)
            else:
                raise ValueError("unsupported deterministic v1.0 model family")
        except (OSError, ValueError, KeyError, np.linalg.LinAlgError, pd.errors.ParserError) as error:
            return self._failed(run_id, request, now, "MODEL_EXECUTION_FAILED", str(error))
        diagnostics_failed = any(
            [
                not diagnostics.converged,
                diagnostics.optimizer_warning,
                diagnostics.variance_boundary,
                diagnostics.rank_deficient,
                diagnostics.nonfinite_inference,
            ]
        )
        output_root.mkdir(parents=True, exist_ok=True)
        run_directory = output_root / sha256_text(request.project_id)[:16] / run_id
        run_directory.mkdir(parents=True, exist_ok=False)
        payload = {
            "parser_version": "statsmodels-result-v1",
            "model_family": request.model_specification.model_family,
            "analysis_dataset_sha256": request.analysis_dataset.canonical_content_sha256,
            "values": values,
            "diagnostics": diagnostics.__dict__,
        }
        output_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        (run_directory / "result.json").write_bytes(output_bytes)
        status = RunStatus.NEEDS_REVIEW if diagnostics_failed else RunStatus.SUCCEEDED
        run = OperatorRun(
            operator_run_id=run_id,
            project_id=request.project_id,
            operator_id=self.operator_id,
            operator_version=self.operator_version,
            request_ref=request.code_artifact.ref,
            input_artifact_refs=[
                request.frozen_dataset.ref,
                request.analysis_dataset.ref,
                request.code_specification.ref,
                request.code_artifact.ref,
                request.code_review.ref,
            ],
            output_artifact_refs=[f"execution-output://{run_id}"],
            environment_ref="environment://statsmodels/v1.0",
            log_ref=f"log://{run_id}",
            status=status,
            started_at=now,
            finished_at=datetime.now(UTC),
        )
        validation = ResultValidationReport(
            report_id=f"result-validation-{uuid4().hex}",
            project_id=request.project_id,
            analysis_mode=AnalysisMode.PYTHON_ONLY,
            validation_mode=ValidationMode.SINGLE_ENGINE,
            execution_run_refs=[run_id],
            input_integrity_passed=True,
            model_integrity_passed=True,
            numeric_output_integrity_passed=not diagnostics.nonfinite_inference,
            passed=not diagnostics_failed,
            finding_refs=[] if not diagnostics_failed else ["finding://v1-model-validation/needs-review"],
            fit_converged=diagnostics.converged,
            optimizer_warning=diagnostics.optimizer_warning,
            variance_boundary=diagnostics.variance_boundary,
            rank_deficient=diagnostics.rank_deficient,
            nonfinite_inference=diagnostics.nonfinite_inference,
            design_matrix_rank=diagnostics.design_matrix_rank,
            design_columns=diagnostics.design_columns,
            group_counts=diagnostics.group_counts,
            sequence_counts=diagnostics.sequence_counts,
            task_period_row_counts=diagnostics.task_period_row_counts,
            variance_boundary_policy_version=self.policy.policy_version,
            variance_boundary_threshold=(
                self.policy.threshold(diagnostics.residual_variance)
                if diagnostics.residual_variance is not None
                else None
            ),
            random_intercept_variance=diagnostics.random_intercept_variance,
            residual_variance=diagnostics.residual_variance,
            random_to_residual_variance_ratio=(
                diagnostics.random_intercept_variance / diagnostics.residual_variance
                if diagnostics.random_intercept_variance is not None
                and diagnostics.residual_variance is not None
                and diagnostics.residual_variance > 0
                else None
            ),
        )
        reproducibility = self._manifest(request, output_bytes)
        return V1ExecutionOutcome(
            execution_run=run,
            result_values=values,
            result_payload_sha256=sha256_bytes(output_bytes),
            result_output_ref=f"execution-output://{run_id}",
            validation_report=validation,
            reproducibility_manifest=reproducibility,
        )

    def _preflight(self, request: V1ExecutionRequest) -> str | None:
        if request.human_execution_approval.project_id != request.project_id:
            return "APPROVAL_PROJECT_SCOPE_MISMATCH"
        if request.code_specification.project_id != request.project_id:
            return "CODE_SPECIFICATION_PROJECT_SCOPE_MISMATCH"
        if request.code_artifact.project_id != request.project_id:
            return "CODE_ARTIFACT_PROJECT_SCOPE_MISMATCH"
        if request.code_artifact.specification_ref != request.code_specification.ref:
            return "CODE_ARTIFACT_SPECIFICATION_MISMATCH"
        if request.executable_plan.project_id != request.project_id:
            return "EXECUTABLE_PLAN_PROJECT_SCOPE_MISMATCH"
        if request.executable_plan_ref != f"executable-plan://{request.executable_plan.executable_plan_id}":
            return "EXECUTABLE_PLAN_REFERENCE_MISMATCH"
        if sha256_text(request.executable_plan.model_dump_json(exclude_none=True)) != request.executable_plan_sha256:
            return "EXECUTABLE_PLAN_HASH_MISMATCH"
        if request.executable_plan.frozen_dataset_ref != request.frozen_dataset.ref:
            return "EXECUTABLE_PLAN_FROZEN_DATASET_REFERENCE_MISMATCH"
        if request.executable_plan.frozen_dataset_sha256 != request.frozen_dataset.canonical_content_sha256:
            return "EXECUTABLE_PLAN_FROZEN_DATASET_HASH_MISMATCH"
        if request.code_specification.executable_plan_ref != request.executable_plan_ref:
            return "CODE_SPECIFICATION_PLAN_REFERENCE_MISMATCH"
        if request.code_specification.frozen_dataset_ref != request.frozen_dataset.ref:
            return "CODE_SPECIFICATION_FROZEN_DATASET_REFERENCE_MISMATCH"
        if request.code_specification.frozen_dataset_sha256 != request.frozen_dataset.canonical_content_sha256:
            return "CODE_SPECIFICATION_FROZEN_DATASET_HASH_MISMATCH"
        if request.code_specification.analysis_dataset_ref != request.analysis_dataset.ref:
            return "CODE_SPECIFICATION_ANALYSIS_DATASET_REFERENCE_MISMATCH"
        if request.code_specification.analysis_dataset_sha256 != request.analysis_dataset.canonical_content_sha256:
            return "CODE_SPECIFICATION_ANALYSIS_DATASET_HASH_MISMATCH"
        expected_template_hash = sha256_text(Path(__file__).read_text(encoding="utf-8"))
        if request.code_specification.deterministic_template_sha256 != expected_template_hash:
            return "DETERMINISTIC_TEMPLATE_IMPLEMENTATION_MISMATCH"
        try:
            self.freeze_service.assert_integrity(request.frozen_dataset)
        except FrozenDatasetIntegrityError:
            return "FROZEN_DATASET_INTEGRITY_MISMATCH"
        try:
            analysis_bytes = Path(request.analysis_dataset.content_uri).read_bytes()
            if sha256_bytes(analysis_bytes) != request.analysis_dataset.raw_bytes_sha256:
                return "ANALYSIS_DATASET_BYTE_HASH_MISMATCH"
            header, rows = read_csv_rows(analysis_bytes)
            if sha256_bytes(canonical_csv_bytes(header, rows)) != request.analysis_dataset.canonical_content_sha256:
                return "ANALYSIS_DATASET_CANONICAL_HASH_MISMATCH"
        except (OSError, UnicodeDecodeError, ValueError):
            return "ANALYSIS_DATASET_UNREADABLE"
        if request.project_id != request.analysis_dataset.project_id:
            return "PROJECT_SCOPE_MISMATCH"
        expected_dataset = self._model_dataset.get(request.model_specification.model_family)
        if expected_dataset is None or expected_dataset not in request.analysis_dataset.dataset_id:
            return "ANALYSIS_DATASET_MODEL_MISMATCH"
        if request.analysis_dataset.source_frozen_dataset_ref != request.frozen_dataset.ref:
            return "FROZEN_DATASET_REFERENCE_MISMATCH"
        if request.analysis_dataset.source_dataset_sha256 != request.frozen_dataset.canonical_content_sha256:
            return "FROZEN_DATASET_HASH_MISMATCH"
        if not request.code_review.passed:
            return "CODE_REVIEW_FAILED"
        current = self._approval_hashes(request)
        approved = request.human_execution_approval
        if approved.approval_status != "approved" or any(
            [
                approved.plan_sha256 != current["plan"],
                approved.code_spec_sha256 != current["code_spec"],
                approved.code_artifact_sha256 != current["code_artifact"],
                approved.code_review_result_sha256 != current["code_review"],
                approved.analysis_dataset_sha256 != current["analysis_dataset"],
                approved.environment_spec_sha256 != current["environment"],
                approved.template_version != self.template_version,
            ]
        ):
            return "APPROVAL_BINDING_MISMATCH"
        return None

    def _fit_primary_lmm(
        self, frame: pd.DataFrame, specification: AnalysisModelSpecification
    ) -> tuple[dict[str, float], _FitDiagnostics]:
        formula = self._formula(specification, "physics_modeling_score")
        result, diagnostics = self._mixed_fit(frame, formula, specification)
        params = result.fe_params
        covariance = result.cov_params().loc[params.index, params.index]
        weights = self._contrast_vector(list(params.index), specification.primary_contrast_weights)
        effect = float(weights @ params.to_numpy())
        variance = float(weights @ covariance.to_numpy() @ weights)
        standard_error = math.sqrt(variance) if variance >= 0 else math.nan
        z_value = effect / standard_error if standard_error > 0 else math.nan
        p_value = 2 * norm.sf(abs(z_value)) if math.isfinite(z_value) else math.nan
        critical = norm.ppf(0.975)
        values = {
            "primary_contrast_estimate": effect,
            "primary_contrast_standard_error": standard_error,
            "primary_contrast_z": z_value,
            "primary_contrast_p": p_value,
            "primary_contrast_ci_lower": effect - critical * standard_error,
            "primary_contrast_ci_upper": effect + critical * standard_error,
        }
        return values, self._with_inference(diagnostics, values)

    def _fit_prompt_lmm(
        self, frame: pd.DataFrame, specification: AnalysisModelSpecification
    ) -> tuple[dict[str, float], _FitDiagnostics]:
        formula = self._formula(specification, "prompt_dependency")
        result, diagnostics = self._mixed_fit(frame, formula, specification)
        values = self._fixed_effect_values(result)
        return values, self._with_inference(diagnostics, values)

    def _fit_transfer_ancova(
        self, frame: pd.DataFrame, specification: AnalysisModelSpecification
    ) -> tuple[dict[str, float], _FitDiagnostics]:
        formula = self._formula(specification, "transfer_score")
        result = sm.OLS.from_formula(formula, data=frame).fit(cov_type="HC3", use_t=True)
        columns = list(result.model.exog_names)
        values = self._fixed_effect_values(result)
        interaction_formula = (
            'transfer_score ~ C(group, Treatment(reference="static_prompt")) * baseline_score'
        )
        interaction = sm.OLS.from_formula(interaction_formula, data=frame).fit(cov_type="HC3", use_t=True)
        interaction_key = next(
            key for key in interaction.params.index if ":baseline_score" in key
        )
        values["slope_homogeneity_interaction_p"] = float(interaction.pvalues[interaction_key])
        diagnostics = _FitDiagnostics(
            converged=True,
            optimizer_warning=False,
            variance_boundary=False,
            rank_deficient=bool(np.linalg.matrix_rank(result.model.exog) < result.model.exog.shape[1]),
            nonfinite_inference=not all(math.isfinite(value) for value in values.values()),
            design_matrix_rank=int(np.linalg.matrix_rank(result.model.exog)),
            design_columns=columns,
            group_counts=_participant_group_counts(frame),
            sequence_counts=_participant_sequence_counts(frame),
            task_period_row_counts=_task_period_counts(frame),
        )
        return values, diagnostics

    def _mixed_fit(
        self, frame: pd.DataFrame, formula: str, specification: AnalysisModelSpecification
    ) -> tuple[MixedLMResults, _FitDiagnostics]:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model = sm.MixedLM.from_formula(
                formula,
                groups=specification.groups_variable or "participant_id",
                re_formula=specification.re_formula or "1",
                data=frame,
            )
            result = model.fit(reml=True, method=["lbfgs"], maxiter=200, disp=False)
        warning_seen = any(issubclass(item.category, ConvergenceWarning) for item in caught)
        random_variance = float(result.cov_re.iloc[0, 0])
        residual_variance = float(result.scale)
        boundary = random_variance <= self.policy.threshold(residual_variance)
        values = self._fixed_effect_values(result)
        diagnostics = _FitDiagnostics(
            converged=bool(result.converged),
            optimizer_warning=warning_seen,
            variance_boundary=boundary,
            rank_deficient=bool(np.linalg.matrix_rank(model.exog) < model.exog.shape[1]),
            nonfinite_inference=not all(math.isfinite(value) for value in values.values()),
            design_matrix_rank=int(np.linalg.matrix_rank(model.exog)),
            design_columns=list(model.exog_names),
            group_counts=_participant_group_counts(frame),
            sequence_counts=_participant_sequence_counts(frame),
            task_period_row_counts=_task_period_counts(frame),
            random_intercept_variance=random_variance,
            residual_variance=residual_variance,
        )
        return result, diagnostics

    @staticmethod
    def _formula(specification: AnalysisModelSpecification, expected_outcome: str) -> str:
        formula = specification.executable_fixed_formula or specification.formula_or_design
        if not formula.startswith(f"{expected_outcome} ~"):
            raise ValueError("model formula does not match the approved outcome")
        return formula

    @staticmethod
    def _contrast_vector(
        columns: list[str], weights: dict[str, float]
    ) -> NDArray[np.float64]:
        if not weights:
            raise ValueError("primary LMM requires pre-registered contrast weights")
        unexpected = set(weights).difference(columns)
        if unexpected:
            raise ValueError("primary contrast refers to unavailable fixed-effect columns")
        return np.asarray([weights.get(column, 0.0) for column in columns], dtype=np.float64)

    @staticmethod
    def _fixed_effect_values(result: object) -> dict[str, float]:
        params = getattr(result, "params")
        bse = getattr(result, "bse")
        pvalues = getattr(result, "pvalues")
        values: dict[str, float] = {}
        for parameter in params.index:
            if "Var" in parameter or "Cov" in parameter:
                continue
            values[f"{parameter}_estimate"] = float(params[parameter])
            values[f"{parameter}_standard_error"] = float(bse[parameter])
            values[f"{parameter}_p"] = float(pvalues[parameter])
        return values

    @staticmethod
    def _with_inference(diagnostics: _FitDiagnostics, values: dict[str, float]) -> _FitDiagnostics:
        return _FitDiagnostics(
            **{**diagnostics.__dict__, "nonfinite_inference": diagnostics.nonfinite_inference or not all(math.isfinite(value) for value in values.values())}
        )

    def _not_started(
        self, run_id: str, request: V1ExecutionRequest, now: datetime, reason: str
    ) -> V1ExecutionOutcome:
        return V1ExecutionOutcome(
            execution_run=OperatorRun(
                operator_run_id=run_id,
                project_id=request.project_id,
                operator_id=self.operator_id,
                operator_version=self.operator_version,
                request_ref=request.code_artifact.ref,
                status=RunStatus.NOT_STARTED,
                error_ref=f"error://statsmodels/{reason.lower()}",
                started_at=now,
                finished_at=now,
            )
        )

    def _failed(
        self, run_id: str, request: V1ExecutionRequest, now: datetime, reason: str, _: str
    ) -> V1ExecutionOutcome:
        return V1ExecutionOutcome(
            execution_run=OperatorRun(
                operator_run_id=run_id,
                project_id=request.project_id,
                operator_id=self.operator_id,
                operator_version=self.operator_version,
                request_ref=request.code_artifact.ref,
                status=RunStatus.FAILED,
                error_ref=f"error://statsmodels/{reason.lower()}",
                started_at=now,
                finished_at=datetime.now(UTC),
            )
        )

    def _approval_hashes(self, request: V1ExecutionRequest) -> dict[str, str]:
        return {
            "plan": sha256_text(request.executable_plan.model_dump_json(exclude_none=True)),
            "code_spec": sha256_text(request.code_specification.model_dump_json(exclude_none=True)),
            "code_artifact": request.code_artifact.sha256,
            "code_review": sha256_text(request.code_review.model_dump_json(exclude_none=True)),
            "analysis_dataset": request.analysis_dataset.canonical_content_sha256,
            "environment": request.environment_spec_sha256,
        }

    def _manifest(self, request: V1ExecutionRequest, output_bytes: bytes) -> ReproducibilityManifest:
        hashes = self._approval_hashes(request)
        dependency_lock = "statsmodels==0.14.6|numpy|pandas|scipy"
        return ReproducibilityManifest(
            manifest_id=f"reproducibility-{uuid4().hex}",
            project_id=request.project_id,
            plan_sha256=hashes["plan"],
            code_spec_sha256=hashes["code_spec"],
            code_artifact_sha256=hashes["code_artifact"],
            frozen_dataset_sha256=request.frozen_dataset.canonical_content_sha256,
            analysis_dataset_sha256=request.analysis_dataset.canonical_content_sha256,
            result_file_sha256=sha256_bytes(output_bytes),
            python_version=platform.python_version(),
            statsmodels_version=importlib.metadata.version("statsmodels"),
            dependency_lock_hash=sha256_text(dependency_lock),
            template_version=self.template_version,
            deterministic_template_sha256=request.code_specification.deterministic_template_sha256,
        )


def _participant_group_counts(frame: pd.DataFrame) -> dict[str, int]:
    return dict(sorted(frame.groupby("group")["participant_id"].nunique().astype(int).to_dict().items()))


def _participant_sequence_counts(frame: pd.DataFrame) -> dict[str, int]:
    unique = frame.drop_duplicates("participant_id")
    return dict(sorted(Counter(f"{row.group}:{row.task_sequence}" for row in unique.itertuples()).items()))


def _task_period_counts(frame: pd.DataFrame) -> dict[str, int]:
    return dict(
        sorted(Counter(f"{row.task_id}:{row.measurement_period}" for row in frame.itertuples()).items())
    )

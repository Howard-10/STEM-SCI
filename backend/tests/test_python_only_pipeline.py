"""Acceptance tests for the CSV + PYTHON_ONLY deterministic MVP path."""

from __future__ import annotations

import os
import stat
from datetime import UTC, datetime
from pathlib import Path

from stem_sci.agents import (
    IndependentReviewAgent,
    ManuscriptNumericClaim,
    ReproducibilityReviewInput,
)
from stem_sci.artifacts.execution_store import InMemoryExecutionStore
from stem_sci.controller import OperatorExecutor
from stem_sci.core.enums import DecisionScope, RunStatus
from stem_sci.research_data.demo import write_synthetic_demo_seed
from stem_sci.research_data.freeze import DataFreezeService
from stem_sci.research_data.models import RawDatasetRef
from stem_sci.research_data.processing import DataProcessingService
from stem_sci.statistics import (
    AnalysisModelSpecification,
    CsvPythonAnalysisOperator,
    ExecutableAnalysisPlan,
    PythonAnalysisRequest,
    SingleEngineResultValidator,
    StatisticalResultCard,
)
from stem_sci.statistics.mode_policy import AnalysisMode
from stem_sci.utils.hash_utils import sha256_bytes


def _approved_mvp_request(tmp_path: Path) -> PythonAnalysisRequest:
    project_id = "synthetic-physics-demo"
    source_path = write_synthetic_demo_seed(tmp_path / "raw" / "physics_demo_seed.csv")
    created_at = datetime.now(UTC)
    raw = RawDatasetRef(
        dataset_id="raw-physics-demo",
        project_id=project_id,
        version=1,
        content_uri=str(source_path),
        sha256=sha256_bytes(source_path.read_bytes()),
        created_at=created_at,
    )
    processed = DataProcessingService().process_csv_identity(
        raw_dataset=raw,
        processing_plan_ref="processing-plan://synthetic-physics-demo/v1",
        processing_approval_ref="approval://synthetic-physics-demo/processing-v1",
        destination_directory=tmp_path / "processed",
    )
    frozen = DataFreezeService().freeze_csv(
        processed_dataset=processed,
        freeze_approval_ref="approval://synthetic-physics-demo/processing-v1",
        destination_directory=tmp_path / "frozen",
    )
    plan = ExecutableAnalysisPlan(
        executable_plan_id="physics-demo-plan-v1",
        project_id=project_id,
        preregistered_plan_ref="prereg-plan://synthetic-physics-demo/v1",
        frozen_dataset_ref=frozen.ref,
        frozen_dataset_sha256=frozen.sha256,
        dataset_schema_ref=frozen.schema_ref,
        variable_mapping={"outcome": "transfer_score", "group": "group"},
        type_confirmations={"transfer_score": "float", "group": "categorical"},
        software_configuration={"engine": "python", "parser": "mvp-csv-v1"},
        analysis_mode=AnalysisMode.PYTHON_ONLY,
        model_specification_refs=["model-spec://synthetic-physics-demo/group-difference"],
        compatibility_gate_ref="gate://schema-compatibility/pass",
    )
    model = AnalysisModelSpecification(
        model_spec_id="group-difference",
        project_id=project_id,
        model_family="group_mean_difference",
        outcome_variables=["transfer_score"],
        predictor_variables=["group"],
        formula_or_design="mean(transfer_score) by group",
        rationale="Transparent MVP comparison for synthetic acceptance data.",
    )
    return PythonAnalysisRequest(
        project_id=project_id,
        frozen_dataset=frozen,
        executable_plan=plan,
        model_specification=model,
        code_artifact_ref="code-artifact://synthetic-physics-demo/mvp-v1",
    )


def test_python_only_pipeline_creates_verified_result_card(tmp_path: Path) -> None:
    request = _approved_mvp_request(tmp_path)
    execution_store = InMemoryExecutionStore()
    outcome = OperatorExecutor(execution_store=execution_store).execute_python_only(
        request, tmp_path / "execution-runs"
    )

    assert outcome.execution_run.status is RunStatus.SUCCEEDED
    assert (
        execution_store.get(request.project_id, outcome.execution_run.operator_run_id)
        == outcome.execution_run
    )
    report = SingleEngineResultValidator().validate(outcome, "validation-python-only-v1")
    assert report.passed is True
    assert report.validation_mode == "SINGLE_ENGINE"
    assert report.execution_status == "execution_verified"
    result_card = StatisticalResultCard.build_from_validation(
        result_id="result-card-python-only-v1",
        project_id=request.project_id,
        execution_run_ref=outcome.execution_run.operator_run_id,
        analysis_plan_ref=f"executable-plan://{request.executable_plan.executable_plan_id}",
        validation_report=report,
        parsed_values=outcome.result_values,
        deterministic_parser_version="python-result-parser-v1",
    )
    assert result_card.execution_status == "execution_verified"
    assert result_card.interpretation_status == "pending_human_review"


def test_tampered_frozen_dataset_blocks_execution(tmp_path: Path) -> None:
    request = _approved_mvp_request(tmp_path)
    frozen_path = Path(request.frozen_dataset.content_uri)
    os.chmod(frozen_path, stat.S_IWRITE | stat.S_IREAD)
    frozen_path.write_text("group,transfer_score\nai_scaffold,999\n", encoding="utf-8")

    outcome = CsvPythonAnalysisOperator().execute(request, tmp_path / "execution-runs")

    assert outcome.execution_run.status is RunStatus.BLOCKED
    assert outcome.execution_run.error_ref == "error://frozen-dataset-integrity"
    assert outcome.result_values == {}


def test_reviewer_flags_manuscript_number_and_targets_only_that_artifact(tmp_path: Path) -> None:
    request = _approved_mvp_request(tmp_path)
    outcome = CsvPythonAnalysisOperator().execute(request, tmp_path / "execution-runs")
    report = SingleEngineResultValidator().validate(outcome, "validation-review-v1")
    result_card = StatisticalResultCard.build_from_validation(
        result_id="result-card-review-v1",
        project_id=request.project_id,
        execution_run_ref=outcome.execution_run.operator_run_id,
        analysis_plan_ref=f"executable-plan://{request.executable_plan.executable_plan_id}",
        validation_report=report,
        parsed_values=outcome.result_values,
        deterministic_parser_version="python-result-parser-v1",
    )
    manuscript_ref = "manuscript://synthetic-physics-demo/v1"
    review = IndependentReviewAgent().review_reproducibility(
        ReproducibilityReviewInput(
            project_id=request.project_id,
            manuscript_ref=manuscript_ref,
            numeric_claims=[
                ManuscriptNumericClaim(
                    claim_ref="claim://synthetic-physics-demo/result-1",
                    result_card_ref=result_card.ref,
                    result_key="transfer_mean_difference_group_2_minus_group_1",
                    reported_value=999.0,
                )
            ],
            statistical_result_cards=[result_card],
        )
    )

    assert review.report.overall_recommendation == "MAJOR_REVISION"
    assert review.findings[0].decision_scope is DecisionScope.ARTIFACT
    assert review.findings[0].blocked_target_ids == [manuscript_ref]
    assert review.revision_requests[0].artifact_ref == manuscript_ref

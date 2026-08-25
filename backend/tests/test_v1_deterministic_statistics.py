"""Acceptance tests for Architecture Freeze v1.0 deterministic statistics."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

from stem_sci.coding.models import CodeArtifact, CodeSpecification
from stem_sci.coding.review import CodeReviewGate
from stem_sci.controller.v1_analysis_pipeline import (
    V1AnalysisPipelineController,
    V1AnalysisPreparationRequest,
)
from stem_sci.agents import IndependentReviewAgent, ReviewPacket
from stem_sci.research_data import (
    DataFreezeService,
    DataProcessingService,
    DeterministicDataProcessor,
    ModelEligibilityEvaluator,
    RawDatasetRef,
    StructuralDataAuditor,
)
from stem_sci.research_data.canonical import read_csv_rows
from stem_sci.research_data.demo import synthetic_demo_manifest, write_synthetic_demo_seed
from stem_sci.statistics import (
    AnalysisModelSpecification,
    ExecutableAnalysisPlan,
    HumanExecutionApproval,
)
from stem_sci.research_protocol import PreregisteredAnalysisPlan
from stem_sci.statistics.mode_policy import AnalysisMode
from stem_sci.statistics.v1_execution import DeterministicStatsmodelsExecutor, V1ExecutionRequest
from stem_sci.utils.hash_utils import sha256_bytes, sha256_text


def _dataset_chain(tmp_path: Path):
    project_id = "v1-demo"
    raw_path = write_synthetic_demo_seed(tmp_path / "input" / "seed.csv")
    raw_content = raw_path.read_bytes()
    raw = RawDatasetRef(
        dataset_id="raw-v1", project_id=project_id, version=1, content_uri=str(raw_path),
        sha256=sha256_bytes(raw_content), raw_bytes_sha256=sha256_bytes(raw_content),
        canonical_content_sha256=synthetic_demo_manifest().generated_dataset_sha256,
        created_at=datetime.now(UTC),
    )
    processed = DataProcessingService().process_csv_identity(
        raw_dataset=raw, processing_plan_ref="processing://v1", processing_approval_ref="approval://processing",
        destination_directory=tmp_path / "processed",
    )
    frozen = DataFreezeService().freeze_csv(
        processed_dataset=processed, freeze_approval_ref="approval://freeze", destination_directory=tmp_path / "frozen"
    )
    audit = StructuralDataAuditor().audit(frozen)
    assert audit.passed and audit.participant_eligibility_manifest is not None
    return project_id, frozen, audit.participant_eligibility_manifest


def _model_spec(project_id: str, family: str) -> AnalysisModelSpecification:
    if family == "linear_mixed_effects_primary":
        return AnalysisModelSpecification(
            model_spec_id="primary-lmm", project_id=project_id, model_family=family,
            outcome_variables=["physics_modeling_score"],
            predictor_variables=["group", "measurement_period", "task_id", "baseline_score"],
            grouping_variables=["participant_id"],
            formula_or_design="physics_modeling_score ~ group * measurement_period + task_id + baseline_score",
            human_readable_formula="physics_modeling_score ~ group * measurement_period + task_id + baseline_score + (1 | participant_id)",
            executable_fixed_formula='physics_modeling_score ~ C(group, Treatment(reference="static_prompt")) * C(measurement_period, Treatment(reference="period1")) + C(task_id, Treatment(reference="A")) + baseline_score',
            groups_variable="participant_id", re_formula="1",
            primary_contrast_weights={
                'C(group, Treatment(reference="static_prompt"))[T.ai_scaffold]': 1.0,
                'C(group, Treatment(reference="static_prompt"))[T.ai_scaffold]:C(measurement_period, Treatment(reference="period1"))[T.period2]': 0.5,
            },
            rationale="Frozen v1.0 primary estimand.",
        )
    if family == "ols_ancova_transfer":
        return AnalysisModelSpecification(
            model_spec_id="transfer-ancova", project_id=project_id, model_family=family,
            outcome_variables=["transfer_score"], predictor_variables=["group", "baseline_score"],
            formula_or_design="transfer_score ~ group + baseline_score",
            human_readable_formula="transfer_score ~ group + baseline_score",
            executable_fixed_formula='transfer_score ~ C(group, Treatment(reference="static_prompt")) + baseline_score',
            rationale="Frozen v1.0 transfer secondary analysis.",
        )
    return AnalysisModelSpecification(
        model_spec_id="prompt-lmm", project_id=project_id, model_family=family,
        outcome_variables=["prompt_dependency"],
        predictor_variables=["group", "measurement_period", "task_id", "baseline_score"],
        grouping_variables=["participant_id"],
        formula_or_design="prompt_dependency ~ group * measurement_period + task_id + baseline_score",
        human_readable_formula="prompt_dependency ~ group * measurement_period + task_id + baseline_score + (1 | participant_id)",
        executable_fixed_formula='prompt_dependency ~ C(group, Treatment(reference="static_prompt")) * C(measurement_period, Treatment(reference="period1")) + C(task_id, Treatment(reference="A")) + baseline_score',
        groups_variable="participant_id", re_formula="1", rationale="Frozen v1.0 dependency secondary analysis.",
    )


def _request(tmp_path: Path, family: str) -> tuple[V1ExecutionRequest, Path]:
    project_id, frozen, participant_manifest = _dataset_chain(tmp_path)
    model_id = {
        "linear_mixed_effects_primary": "primary_lmm",
        "ols_ancova_transfer": "transfer_ancova",
        "linear_mixed_effects_prompt_dependency": "prompt_dependency_lmm",
    }[family]
    eligibility = ModelEligibilityEvaluator().evaluate(
        frozen_dataset=frozen, participant_manifest=participant_manifest, model_id=model_id
    )
    analysis = DeterministicDataProcessor().create_analysis_dataset(
        frozen_dataset=frozen, participant_manifest=participant_manifest, model_manifest=eligibility,
        data_processing_plan_ref="processing://v1", analysis_dataset_specification_ref=f"analysis-dataset-spec://{model_id}",
        model_specification_ref=f"model-spec://{family}", destination_directory=tmp_path / "analysis",
    )
    plan = ExecutableAnalysisPlan(
        executable_plan_id=f"plan-{family}",
        project_id=project_id,
        preregistered_plan_ref="preregistered-plan://v1",
        frozen_dataset_ref=frozen.ref,
        frozen_dataset_sha256=frozen.canonical_content_sha256,
        dataset_schema_ref=frozen.schema_ref,
        variable_mapping={"outcome": _model_spec(project_id, family).outcome_variables[0]},
        type_confirmations={"outcome": "numeric"},
        software_configuration={"engine": "python"},
        analysis_mode=AnalysisMode.PYTHON_ONLY,
        model_specification_refs=[f"model-spec://{family}"],
        compatibility_gate_ref="gate://schema-compatibility/pass",
    )
    spec = CodeSpecification(
        specification_id=f"code-spec-{family}", language="python", entrypoint="analysis.py", purpose="research_analysis",
        project_id=project_id, executable_plan_ref=f"executable-plan://{plan.executable_plan_id}", frozen_dataset_ref=frozen.ref,
        frozen_dataset_sha256=frozen.canonical_content_sha256, analysis_dataset_ref=analysis.ref,
        analysis_dataset_sha256=analysis.canonical_content_sha256, model_specification_ref=f"model-spec://{family}",
        approved_variable_names=list(read_csv_rows(Path(analysis.content_uri).read_bytes())[0]),
        deterministic_template_sha256=sha256_text(
            (Path(__file__).parents[1] / "src" / "stem_sci" / "statistics" / "v1_execution.py").read_text(encoding="utf-8")
        ),
        analysis_parameters={"model_family": family, "requires_analysis_dataset": "true"},
        execution_policy_ref="policy://v1", output_types=["result.json"],
    )
    code = tmp_path / "code.py"
    code.write_text("# deterministic template\n", encoding="utf-8")
    artifact = CodeArtifact(
        artifact_id=f"artifact-{family}", project_id=project_id, specification_ref=spec.ref,
        content_uri=str(code), sha256=sha256_bytes(code.read_bytes()), created_at=datetime.now(UTC),
        source_specification_sha256=sha256_text(spec.model_dump_json(exclude_none=True)),
    )
    review = CodeReviewGate().review(review_id=f"review-{family}", specification=spec, artifact=artifact)
    # v1 deterministic executor checks content identity; the code itself is not executed here.
    code_review_hash = sha256_text(review.model_dump_json(exclude_none=True))
    plan_hash = sha256_text(plan.model_dump_json(exclude_none=True))
    environment_hash = sha256_text("statsmodels=0.14.6|python-only")
    approval = HumanExecutionApproval(
        approval_id=f"approval-{family}", project_id=project_id, approved_at=datetime.now(UTC), approved_by="tester",
        approval_status="approved", plan_sha256=plan_hash, code_spec_sha256=sha256_text(spec.model_dump_json(exclude_none=True)),
        code_artifact_sha256=artifact.sha256, code_review_result_sha256=code_review_hash,
        analysis_dataset_sha256=analysis.canonical_content_sha256, environment_spec_sha256=environment_hash,
        template_version="statsmodels-v1.0",
    )
    return V1ExecutionRequest(
        project_id=project_id, frozen_dataset=frozen, analysis_dataset=analysis, executable_plan=plan,
        executable_plan_ref=f"executable-plan://{plan.executable_plan_id}",
        executable_plan_sha256=plan_hash, model_specification=_model_spec(project_id, family), code_specification=spec,
        code_artifact=artifact, code_review=review, human_execution_approval=approval,
        environment_spec_sha256=environment_hash,
    ), tmp_path / "runs"


def test_demo_seed_is_canonical_and_reproducible(tmp_path: Path) -> None:
    first = write_synthetic_demo_seed(tmp_path / "one.csv")
    second = write_synthetic_demo_seed(tmp_path / "two.csv")
    manifest = synthetic_demo_manifest()
    assert sha256_bytes(first.read_bytes()) == sha256_bytes(second.read_bytes())
    assert sha256_bytes(first.read_bytes()) == manifest.generated_dataset_sha256


def test_v1_frozen_preregistration_requires_estimand_contrast_and_outcome_definition() -> None:
    base = {
        "plan_id": "pap-v1", "primary_outcomes": ["physics_modeling_score"],
        "confirmatory_models": ["linear_mixed_effects_primary"],
        "missing_data_strategy": "model-specific eligibility only",
        "outlier_strategy": "report only; no automatic deletion",
        "alpha": 0.05, "multiple_comparison_strategy": "primary contrast only",
        "exploratory_analysis_policy": "amendment plus human approval",
        "contract_version": "v1.0", "status": "frozen", "approval_ref": "approval://pap/v1",
        "frozen_at": datetime.now(UTC),
    }
    import pytest

    with pytest.raises(ValueError, match="primary_estimand_ref"):
        PreregisteredAnalysisPlan(**base)
    plan = PreregisteredAnalysisPlan(
        **base,
        primary_estimand_ref="estimand://primary/v1",
        primary_contrast_ref="contrast://primary/v1",
        outcome_operational_definition_refs=["outcome-definition://prompt-dependency/v1"],
        inference_contract_ref="inference-contract://statsmodels/v1",
    )
    assert plan.status == "frozen"


def test_secondary_outcome_missing_does_not_fail_primary_eligibility(tmp_path: Path) -> None:
    _, frozen, participant_manifest = _dataset_chain(tmp_path)
    path = Path(frozen.content_uri)
    header, rows = read_csv_rows(path.read_bytes())
    for row in rows:
        if row["participant_id"] == "seed-001" and row["task_id"] == "C":
            row["transfer_score"] = ""
    # This scenario uses a fresh canonical frozen reference only for eligibility proof.
    from stem_sci.research_data.canonical import canonical_csv_bytes
    altered = canonical_csv_bytes(header, rows)
    path.chmod(0o666)
    path.write_bytes(altered)
    altered_frozen = frozen.model_copy(update={"sha256": sha256_bytes(altered), "canonical_content_sha256": sha256_bytes(altered)})
    primary = ModelEligibilityEvaluator().evaluate(
        frozen_dataset=altered_frozen, participant_manifest=participant_manifest, model_id="primary_lmm"
    )
    transfer = ModelEligibilityEvaluator().evaluate(
        frozen_dataset=altered_frozen, participant_manifest=participant_manifest, model_id="transfer_ancova"
    )
    assert next(item for item in primary.records if item.participant_id == "seed-001").eligible
    assert not next(item for item in transfer.records if item.participant_id == "seed-001").eligible


def test_primary_lmm_uses_full_covariance_contrast_and_validates(tmp_path: Path) -> None:
    request, output = _request(tmp_path, "linear_mixed_effects_primary")
    outcome = DeterministicStatsmodelsExecutor().execute(request, output)
    assert outcome.execution_run.status.value == "SUCCEEDED"
    assert outcome.validation_report is not None and outcome.validation_report.passed
    assert outcome.reproducibility_manifest is not None
    frame = pd.read_csv(request.analysis_dataset.content_uri)
    model = sm.MixedLM.from_formula(request.model_specification.executable_fixed_formula, groups="participant_id", re_formula="1", data=frame)
    result = model.fit(reml=True, method=["lbfgs"], maxiter=200, disp=False)
    parameters = result.fe_params
    vector = np.array([request.model_specification.primary_contrast_weights.get(name, 0.0) for name in parameters.index])
    expected = float(vector @ parameters.to_numpy())
    variance = float(vector @ result.cov_params().loc[parameters.index, parameters.index].to_numpy() @ vector)
    linear_contrast = result.t_test(vector.reshape(1, -1), use_t=False)
    assert math.isclose(outcome.result_values["primary_contrast_estimate"], expected)
    assert math.isclose(outcome.result_values["primary_contrast_standard_error"], math.sqrt(variance))
    assert math.isclose(expected, float(linear_contrast.effect[0]))
    assert math.isclose(math.sqrt(variance), float(linear_contrast.sd[0, 0]))


def test_transfer_ancova_and_prompt_lmm_execute(tmp_path: Path) -> None:
    for family in ("ols_ancova_transfer", "linear_mixed_effects_prompt_dependency"):
        request, output = _request(tmp_path / family, family)
        outcome = DeterministicStatsmodelsExecutor().execute(request, output)
        assert outcome.execution_run.status.value == "SUCCEEDED"
        assert outcome.validation_report is not None and outcome.validation_report.passed


def test_execution_refuses_changed_content_after_approval(tmp_path: Path) -> None:
    request, output = _request(tmp_path, "ols_ancova_transfer")
    tampered = request.model_copy(
        update={"environment_spec_sha256": sha256_text("changed-environment")}
    )
    outcome = DeterministicStatsmodelsExecutor().execute(tampered, output)
    assert outcome.execution_run.status.value == "NOT_STARTED"
    assert outcome.execution_run.error_ref == "error://statsmodels/approval_binding_mismatch"


def test_analysis_dataset_hash_change_blocks_before_statistics(tmp_path: Path) -> None:
    request, output = _request(tmp_path, "ols_ancova_transfer")
    path = Path(request.analysis_dataset.content_uri)
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    outcome = DeterministicStatsmodelsExecutor().execute(request, output)
    assert outcome.execution_run.status.value == "NOT_STARTED"
    assert outcome.execution_run.error_ref == "error://statsmodels/analysis_dataset_byte_hash_mismatch"


def test_controller_owned_v1_chain_prepares_approves_and_executes(tmp_path: Path) -> None:
    project_id, frozen, _ = _dataset_chain(tmp_path)
    plan = ExecutableAnalysisPlan(
        executable_plan_id="v1-primary-plan",
        project_id=project_id,
        preregistered_plan_ref="preregistered-plan://v1-primary",
        frozen_dataset_ref=frozen.ref,
        frozen_dataset_sha256=frozen.canonical_content_sha256,
        dataset_schema_ref=frozen.schema_ref,
        variable_mapping={"outcome": "physics_modeling_score"},
        type_confirmations={"physics_modeling_score": "float"},
        software_configuration={"engine": "python", "statsmodels": "0.14.6"},
        analysis_mode=AnalysisMode.PYTHON_ONLY,
        model_specification_refs=["model-spec://primary-lmm"],
        compatibility_gate_ref="gate://schema-compatibility/pass",
    )
    plan_hash = sha256_text(plan.model_dump_json(exclude_none=True))
    request = V1AnalysisPreparationRequest(
        project_id=project_id,
        frozen_dataset=frozen,
        executable_plan=plan,
        executable_plan_sha256=plan_hash,
        model_specification=_model_spec(project_id, "linear_mixed_effects_primary"),
        data_processing_plan_ref="processing-plan://approved/v1",
        analysis_dataset_specification_ref="analysis-dataset-spec://primary-lmm/v1",
        environment_spec_sha256=sha256_text("python|statsmodels==0.14.6|template=v1"),
    )
    controller = V1AnalysisPipelineController(
        artifact_root=tmp_path / "artifacts", output_root=tmp_path / "runs"
    )
    prepared = controller.prepare(request)
    assert not prepared.blocked
    assert prepared.structural_audit.passed
    assert prepared.model_eligibility is not None
    assert prepared.model_eligibility.passed_minimum_coverage
    assert prepared.code_review is not None and prepared.code_review.passed
    approval = controller.approve_execution(
        request=request, prepared=prepared, approved_by="human-reviewer"
    )
    result = controller.execute(request=request, prepared=prepared, approval=approval)
    assert result.execution_outcome is not None
    assert result.execution_outcome.execution_run.status.value == "SUCCEEDED"
    assert result.statistical_result_card is not None
    assert result.statistical_result_card.execution_status.value == "execution_verified"
    assert result.next_route == "WAITING_HUMAN"


def test_independent_reviewer_detects_execution_package_hash_mismatch(tmp_path: Path) -> None:
    project_id, frozen, _ = _dataset_chain(tmp_path)
    plan = ExecutableAnalysisPlan(
        executable_plan_id="review-plan", project_id=project_id,
        preregistered_plan_ref="preregistered-plan://review", frozen_dataset_ref=frozen.ref,
        frozen_dataset_sha256=frozen.canonical_content_sha256, dataset_schema_ref=frozen.schema_ref,
        variable_mapping={"outcome": "physics_modeling_score"},
        type_confirmations={"physics_modeling_score": "float"},
        software_configuration={"engine": "python"}, analysis_mode=AnalysisMode.PYTHON_ONLY,
        model_specification_refs=["model-spec://primary-lmm"], compatibility_gate_ref="gate://pass",
    )
    request = V1AnalysisPreparationRequest(
        project_id=project_id, frozen_dataset=frozen, executable_plan=plan,
        executable_plan_sha256=sha256_text(plan.model_dump_json(exclude_none=True)),
        model_specification=_model_spec(project_id, "linear_mixed_effects_primary"),
        data_processing_plan_ref="processing://review", analysis_dataset_specification_ref="dataset-spec://review",
        environment_spec_sha256=sha256_text("review-environment"),
    )
    controller = V1AnalysisPipelineController(
        artifact_root=tmp_path / "artifacts", output_root=tmp_path / "runs"
    )
    prepared = controller.prepare(request)
    approval = controller.approve_execution(request=request, prepared=prepared, approved_by="reviewer")
    result = controller.execute(request=request, prepared=prepared, approval=approval)
    assert result.execution_outcome is not None
    assert result.execution_outcome.validation_report is not None
    assert result.execution_outcome.reproducibility_manifest is not None
    assert result.statistical_result_card is not None
    assert prepared.code_specification is not None
    assert prepared.code_artifact is not None
    assert prepared.code_review is not None
    assert prepared.analysis_dataset is not None
    mismatched_manifest = result.execution_outcome.reproducibility_manifest.model_copy(
        update={"code_artifact_sha256": sha256_text("tampered-code")}
    )
    review = IndependentReviewAgent().review_execution_packet(
        ReviewPacket(
            project_id=project_id, study_protocol_ref="protocol://approved/v1",
            preregistered_plan_ref=plan.preregistered_plan_ref,
            code_specification=prepared.code_specification, code_artifact=prepared.code_artifact,
            code_review_result=prepared.code_review, analysis_dataset=prepared.analysis_dataset,
            execution_run=result.execution_outcome.execution_run,
            validation_report=result.execution_outcome.validation_report,
            reproducibility_manifest=mismatched_manifest,
            statistical_result_cards=[result.statistical_result_card],
        )
    )
    assert review.report.overall_recommendation == "BLOCK"
    assert review.findings[0].decision_scope.value == "STAGE"

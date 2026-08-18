"""Acceptance tests for the Controller-owned research-code execution chain."""

from __future__ import annotations

import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from stem_sci.coding import (
    CodeArtifactStore,
    CodeGenerationRequest,
    CodeReviewGate,
    CodeSpecificationCompiler,
    CodexCliCodingProvider,
    CodingProviderUnavailable,
    DeterministicTemplateCodingProvider,
    ResearchCodeSandbox,
)
from stem_sci.controller.analysis_execution import (
    ResearchAnalysisExecutionRequest,
    ResearchAnalysisExecutionService,
)
from stem_sci.core.enums import RunStatus
from stem_sci.operators.models import OperatorRun
from stem_sci.research_data.demo import write_synthetic_demo_seed
from stem_sci.research_data.freeze import DataFreezeService
from stem_sci.research_data.models import RawDatasetRef
from stem_sci.research_data.processing import DataProcessingService
from stem_sci.statistics import (
    AnalysisModelSpecification,
    CrossEngineResultValidator,
    ExecutableAnalysisPlan,
    PythonExecutionOutcome,
    SpssAdapter,
    SpssAnalysisRequest,
    SpssExecutionOutcome,
)
from stem_sci.statistics.mode_policy import AnalysisMode
from stem_sci.statistics.spss_syntax import (
    SpssSyntaxSpecificationCompiler,
    SpssSyntaxTemplateProvider,
)
from stem_sci.utils.hash_utils import sha256_bytes
from stem_sci.research_data.canonical import read_csv_rows


def _analysis_inputs(tmp_path: Path, mode: AnalysisMode = AnalysisMode.PYTHON_ONLY) -> tuple[
    RawDatasetRef, ExecutableAnalysisPlan, AnalysisModelSpecification
]:
    project_id = "synthetic-physics-research-code"
    source_path = write_synthetic_demo_seed(tmp_path / "raw" / "physics.csv")
    now = datetime.now(UTC)
    raw = RawDatasetRef(
        dataset_id="raw-physics",
        project_id=project_id,
        version=1,
        content_uri=str(source_path),
        sha256=sha256_bytes(source_path.read_bytes()),
        created_at=now,
    )
    processed = DataProcessingService().process_csv_identity(
        raw_dataset=raw,
        processing_plan_ref="processing-plan://physics/v1",
        processing_approval_ref="approval://physics/processing-v1",
        destination_directory=tmp_path / "processed",
    )
    frozen = DataFreezeService().freeze_csv(
        processed_dataset=processed,
        freeze_approval_ref="approval://physics/freeze-v1",
        destination_directory=tmp_path / "frozen",
    )
    model = AnalysisModelSpecification(
        model_spec_id="group-difference-v1",
        project_id=project_id,
        model_family="group_mean_difference",
        outcome_variables=["transfer_score"],
        predictor_variables=["group"],
        grouping_variables=["group"],
        formula_or_design="mean(transfer_score) by group",
        rationale="Transparent synthetic acceptance analysis.",
    )
    plan = ExecutableAnalysisPlan(
        executable_plan_id="physics-executable-v1",
        project_id=project_id,
        preregistered_plan_ref="preregistered-plan://physics/v1",
        frozen_dataset_ref=frozen.ref,
        frozen_dataset_sha256=frozen.sha256,
        dataset_schema_ref=frozen.schema_ref,
        variable_mapping={"outcome": "transfer_score", "group": "group"},
        type_confirmations={"transfer_score": "float", "group": "categorical"},
        software_configuration={"engine": "python"},
        analysis_mode=mode,
        model_specification_refs=[f"model-spec://{model.model_spec_id}"],
        compatibility_gate_ref="gate://schema-compatibility/pass",
    )
    return raw, plan, model


def _frozen_from_raw(tmp_path: Path, mode: AnalysisMode = AnalysisMode.PYTHON_ONLY):
    raw, plan, model = _analysis_inputs(tmp_path, mode)
    processed = DataProcessingService().process_csv_identity(
        raw_dataset=raw,
        processing_plan_ref="processing-plan://physics/v1",
        processing_approval_ref="approval://physics/processing-v1",
        destination_directory=tmp_path / "processed-again",
    )
    frozen = DataFreezeService().freeze_csv(
        processed_dataset=processed,
        freeze_approval_ref="approval://physics/freeze-v1",
        destination_directory=tmp_path / "frozen-again",
    )
    # The plan must point to the fresh frozen copy made above.
    return frozen, plan.model_copy(
        update={
            "frozen_dataset_ref": frozen.ref,
            "frozen_dataset_sha256": frozen.sha256,
            "dataset_schema_ref": frozen.schema_ref,
        }
    ), model


def test_controller_owned_template_chain_runs_real_python_artifact(tmp_path: Path) -> None:
    frozen, plan, model = _frozen_from_raw(tmp_path)
    artifact_store = CodeArtifactStore(tmp_path / "code-artifacts")
    service = ResearchAnalysisExecutionService(
        coding_provider=DeterministicTemplateCodingProvider(artifact_store),
        output_root=tmp_path / "runs",
    )

    result = service.execute_python_only(
        ResearchAnalysisExecutionRequest(
            project_id=frozen.project_id,
            frozen_dataset=frozen,
            executable_plan=plan,
            model_specification=model,
            execution_approval_ref="approval://physics/execution-v1",
        )
    )

    assert result.code_specification.purpose == "research_analysis"
    assert result.code_review.gate_result.decision == "PASS"
    assert result.sandbox_outcome.execution_run.status is RunStatus.SUCCEEDED
    assert result.validation_report is not None and result.validation_report.passed is True
    assert result.validation_report.validation_mode == "SINGLE_ENGINE"
    assert result.statistical_result_card is not None
    assert result.statistical_result_card.execution_status == "execution_verified"
    _, rows = read_csv_rows(Path(frozen.content_uri).read_bytes())
    means = {
        group: sum(float(row["transfer_score"]) for row in rows if row["task_id"] == "C" and row["group"] == group)
        / sum(1 for row in rows if row["task_id"] == "C" and row["group"] == group)
        for group in ("ai_scaffold", "static_prompt")
    }
    assert result.statistical_result_card.values[
        "transfer_mean_difference_group_2_minus_group_1"
    ] == pytest.approx(means["static_prompt"] - means["ai_scaffold"])


def test_tampered_frozen_data_blocks_sandbox_before_code_runs(tmp_path: Path) -> None:
    frozen, plan, model = _frozen_from_raw(tmp_path)
    frozen_path = Path(frozen.content_uri)
    os.chmod(frozen_path, stat.S_IWRITE | stat.S_IREAD)
    frozen_path.write_text("group,transfer_score\nai_scaffold,999\n", encoding="utf-8")
    service = ResearchAnalysisExecutionService(
        coding_provider=DeterministicTemplateCodingProvider(CodeArtifactStore(tmp_path / "code")),
        output_root=tmp_path / "runs",
    )

    result = service.execute_python_only(
        ResearchAnalysisExecutionRequest(
            project_id=frozen.project_id,
            frozen_dataset=frozen,
            executable_plan=plan,
            model_specification=model,
            execution_approval_ref="approval://physics/execution-v1",
        )
    )

    assert result.sandbox_outcome.execution_run.status is RunStatus.BLOCKED
    assert result.sandbox_outcome.warning_codes == ["FROZEN_DATASET_INTEGRITY_FAILED"]
    assert result.statistical_result_card is None


def test_code_review_blocks_network_capable_python_before_sandbox(tmp_path: Path) -> None:
    frozen, plan, model = _frozen_from_raw(tmp_path)
    specification = CodeSpecificationCompiler().compile_python(
        specification_id="code-spec-malicious",
        executable_plan=plan,
        frozen_dataset=frozen,
        model_specification=model,
    )
    artifact = CodeArtifactStore(tmp_path / "code").put(
        project_id=frozen.project_id,
        specification=specification,
        content="import socket\nprint('unsafe')\n",
        language="python",
        provider_id="codex_cli",
        provider_version="test",
    )
    review = CodeReviewGate().review(
        review_id="review-malicious", specification=specification, artifact=artifact
    )
    outcome = ResearchCodeSandbox().execute(
        project_id=frozen.project_id,
        frozen_dataset=frozen,
        specification=specification,
        artifact=artifact,
        review=review,
        output_root=tmp_path / "runs",
    )

    assert review.passed is False
    assert "PROHIBITED_IMPORT" in review.finding_codes
    assert outcome.execution_run.status is RunStatus.BLOCKED
    assert outcome.warning_codes == ["CODE_REVIEW_FAILED"]


def test_codex_provider_is_fail_closed_when_cli_cannot_be_resolved(tmp_path: Path) -> None:
    frozen, plan, model = _frozen_from_raw(tmp_path)
    specification = CodeSpecificationCompiler().compile_python(
        specification_id="code-spec-codex", executable_plan=plan, frozen_dataset=frozen, model_specification=model
    )
    provider = CodexCliCodingProvider(
        CodeArtifactStore(tmp_path / "code"), command="definitely-not-a-codex-command"
    )

    assert provider.health_reason() == "CODEX_CLI_NOT_FOUND"
    with pytest.raises(CodingProviderUnavailable, match="CODEX_CLI_NOT_FOUND"):
        provider.generate(CodeGenerationRequest(project_id=frozen.project_id, specification=specification))


def test_non_template_codex_candidate_requires_human_code_approval(tmp_path: Path) -> None:
    frozen, plan, model = _frozen_from_raw(tmp_path)
    specification = CodeSpecificationCompiler().compile_python(
        specification_id="code-spec-candidate",
        executable_plan=plan,
        frozen_dataset=frozen,
        model_specification=model,
    )
    artifact = CodeArtifactStore(tmp_path / "code").put(
        project_id=frozen.project_id,
        specification=specification,
        content="# STEM_SCI_REVIEWED_TEMPLATE_V1\nimport csv\nprint('candidate')\n",
        language="python",
        provider_id="codex_cli",
        provider_version="test",
    )

    review = CodeReviewGate().review(
        review_id="review-codex-candidate", specification=specification, artifact=artifact
    )

    assert review.passed is True
    assert review.requires_human_approval is True
    assert review.gate_result.decision == "WAITING_HUMAN"


def test_spss_adapter_blocks_dual_run_when_runtime_is_not_available(tmp_path: Path) -> None:
    frozen, plan, model = _frozen_from_raw(tmp_path, AnalysisMode.SPSS_PYTHON_DUAL)
    syntax_specification = SpssSyntaxSpecificationCompiler().compile(
        specification_id="spss-spec-v1",
        executable_plan=plan,
        frozen_dataset=frozen,
        model_specification=model,
    )
    syntax = SpssSyntaxTemplateProvider(CodeArtifactStore(tmp_path / "syntax")).generate(
        CodeGenerationRequest(project_id=frozen.project_id, specification=syntax_specification)
    )
    adapter = SpssAdapter(executable=tmp_path / "missing-stats.exe")

    outcome = adapter.execute(
        SpssAnalysisRequest(
            project_id=frozen.project_id,
            frozen_dataset=frozen,
            executable_plan=plan,
            model_specification=model,
            syntax_artifact=syntax,
            syntax_review_ref="code-review://spss-v1",
        ),
        tmp_path / "runs",
    )

    assert adapter.detect().available is False
    assert "{{FROZEN_DATASET_PATH}}" in Path(syntax.content_uri).read_text(encoding="utf-8")
    assert outcome.execution_run.status is RunStatus.BLOCKED
    assert outcome.execution_run.error_ref == "error://spss/SPSS_EXECUTABLE_NOT_FOUND"


def test_dual_validator_requires_identical_result_key_set_and_numbers(tmp_path: Path) -> None:
    frozen, plan, model = _frozen_from_raw(tmp_path, AnalysisMode.SPSS_PYTHON_DUAL)
    python_run = OperatorRun(
        operator_run_id="python-run", project_id=frozen.project_id, operator_id="python_analysis",
        operator_version="test", request_ref="code-artifact://python", status=RunStatus.SUCCEEDED,
    )
    spss_run = OperatorRun(
        operator_run_id="spss-run", project_id=frozen.project_id, operator_id="spss_analysis",
        operator_version="test", request_ref="code-artifact://spss", status=RunStatus.SUCCEEDED,
    )
    values = {"group_1_n": 3.0, "group_2_n": 3.0, "difference": -15.3333333333}
    outcome = CrossEngineResultValidator().validate(
        report_id="validation-dual-v1",
        consistency_report_id="consistency-dual-v1",
        python_outcome=PythonExecutionOutcome(
            execution_run=python_run, frozen_dataset=frozen, executable_plan=plan,
            model_specification=model, result_values=values,
        ),
        spss_outcome=SpssExecutionOutcome(execution_run=spss_run, result_values=values),
    )

    assert outcome.consistency_report.passed is True
    assert outcome.validation_report.validation_mode == "CROSS_ENGINE"
    assert outcome.validation_report.execution_status == "cross_engine_verified"

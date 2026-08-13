"""Tests for the analysis/review boundaries introduced before real execution."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from stem_sci.agents import (
    AgentInput,
    DataAnalysisAgent,
    DataAnalysisPostExecutionInput,
    DataAnalysisPreAnalysisInput,
    IndependentReviewAgent,
    ReviewFinding,
)
from stem_sci.core.enums import DecisionScope
from stem_sci.statistics.models import (
    AnalysisModelSpecification,
    AnalysisPlanAmendment,
    ExecutionStatus,
    ResultValidationReport,
    StatisticalResultCard,
    SubstantiveAnalysisChange,
    ValidationMode,
)
from stem_sci.statistics.mode_policy import AnalysisMode


def test_data_analysis_agent_proposes_specs_without_operator_requests() -> None:
    agent = DataAnalysisAgent()
    result = agent.run(
        AgentInput(
            agent_run_id="analysis-boundary-1",
            task_ref="project-1:pre-analysis",
            context_bundle_ref="context://project-1/pre-analysis",
            allowed_tool_capabilities=[],
            allowed_output_types=list(agent.allowed_output_types),
            policy_version="policy-v1",
            prompt_template_version="analysis-v1",
        )
    )

    assert result.tool_requests == []
    assert "StatisticalResultCardCandidate" not in " ".join(result.candidate_artifact_refs)
    assert "DataAuditSpecification" in " ".join(result.candidate_artifact_refs)


def test_pre_analysis_requires_frozen_preregistration_and_proposes_no_results() -> None:
    agent = DataAnalysisAgent()
    result = agent.run_pre_analysis(
        DataAnalysisPreAnalysisInput(
            agent_run_id="analysis-pre-1",
            project_id="project-1",
            task_ref="project-1:pre-analysis",
            study_protocol_ref="protocol://project-1/v1",
            preregistered_plan_ref="prereg-plan://project-1/v1",
            preregistered_plan_status="frozen",
            preregistration_approval_ref="approval://project-1/prereg",
            data_collection_schema_ref="schema://collection/v1",
            variable_dictionary_ref="dictionary://collection/v1",
            analysis_mode=AnalysisMode.PYTHON_ONLY,
            model_specification_refs=["model-spec://project-1/main"],
            required_variables=["group", "transfer_score"],
            missingness_checks=["report missingness by group"],
            range_and_type_checks=["transfer_score must be finite numeric"],
            privacy_checks=["reject direct identifiers"],
            proposed_processing_steps=["apply approved processing plan only"],
            missing_data_strategy_ref="prereg-plan://project-1/missing-data",
            diagnostic_checks=["inspect residual distribution"],
            robustness_checks=["report pre-specified sensitivity analysis"],
        )
    )

    assert result.tool_requests == []
    assert all("StatisticalResultCard" not in ref for ref in result.candidate_artifact_refs)
    assert any("ExecutableAnalysisPlanCandidate" in ref for ref in result.candidate_artifact_refs)


def test_pre_analysis_rejects_an_unfrozen_preregistered_plan() -> None:
    with pytest.raises(ValidationError, match="preregistered_plan_status"):
        DataAnalysisPreAnalysisInput(
            agent_run_id="analysis-pre-unfrozen",
            project_id="project-1",
            task_ref="project-1:pre-analysis",
            study_protocol_ref="protocol://project-1/v1",
            preregistered_plan_ref="prereg-plan://project-1/v1",
            preregistered_plan_status="approved",  # type: ignore[arg-type]
            preregistration_approval_ref="approval://project-1/prereg",
            data_collection_schema_ref="schema://collection/v1",
            variable_dictionary_ref="dictionary://collection/v1",
            analysis_mode=AnalysisMode.PYTHON_ONLY,
            model_specification_refs=["model-spec://project-1/main"],
            required_variables=["group", "transfer_score"],
            missingness_checks=["report missingness by group"],
            range_and_type_checks=["transfer_score must be finite numeric"],
            privacy_checks=["reject direct identifiers"],
            proposed_processing_steps=["apply approved processing plan only"],
            missing_data_strategy_ref="prereg-plan://project-1/missing-data",
            diagnostic_checks=["inspect residual distribution"],
            robustness_checks=["report pre-specified sensitivity analysis"],
        )


def test_interpretation_requires_verified_result_and_reviewer_is_read_only() -> None:
    with pytest.raises(ValidationError):
        DataAnalysisPostExecutionInput(
            agent_run_id="analysis-post-1",
            project_id="project-1",
            task_ref="project-1:interpret",
            statistical_result_card_ref="result-card://project-1/v1",
            execution_status=ExecutionStatus.GENERATED,
        )

    finding = ReviewFinding(
        finding_id="finding-1",
        reviewer_type="reproducibility",
        artifact_ref="manuscript://project-1/v1",
        severity="major",
        category="reproducibility",
        description="A manuscript number lacks a result-card reference.",
        suggested_action="Return only the manuscript artifact for revision.",
        decision_scope=DecisionScope.ARTIFACT,
        blocked_target_ids=["manuscript://project-1/v1"],
    )
    assert finding.decision_scope is DecisionScope.ARTIFACT
    assert IndependentReviewAgent.capability().allowed_tool_capabilities == []


def test_result_validation_enforces_python_only_and_dual_engine_labels() -> None:
    python_report = ResultValidationReport(
        report_id="validation-python-1",
        project_id="project-1",
        analysis_mode=AnalysisMode.PYTHON_ONLY,
        validation_mode=ValidationMode.SINGLE_ENGINE,
        execution_run_refs=["execution-run://python/1"],
        input_integrity_passed=True,
        model_integrity_passed=True,
        numeric_output_integrity_passed=True,
        passed=True,
    )
    assert python_report.execution_status is ExecutionStatus.EXECUTION_VERIFIED
    result = StatisticalResultCard.build_from_validation(
        result_id="result-1",
        project_id="project-1",
        execution_run_ref="execution-run://python/1",
        analysis_plan_ref="executable-plan://project-1/v1",
        validation_report=python_report,
        parsed_values={"estimate": 0.25},
        deterministic_parser_version="result-parser-v1",
    )
    assert result.execution_status is ExecutionStatus.EXECUTION_VERIFIED

    dual_report = ResultValidationReport(
        report_id="validation-dual-1",
        project_id="project-1",
        analysis_mode=AnalysisMode.SPSS_PYTHON_DUAL,
        validation_mode=ValidationMode.CROSS_ENGINE,
        execution_run_refs=["execution-run://spss/1", "execution-run://python/1"],
        input_integrity_passed=True,
        model_integrity_passed=True,
        numeric_output_integrity_passed=True,
        result_consistency_report_ref="consistency://project-1/v1",
        passed=True,
    )
    assert dual_report.execution_status is ExecutionStatus.CROSS_ENGINE_VERIFIED

    with pytest.raises(ValidationError):
        ResultValidationReport(
            report_id="validation-invalid-1",
            project_id="project-1",
            analysis_mode=AnalysisMode.PYTHON_ONLY,
            validation_mode=ValidationMode.CROSS_ENGINE,
            execution_run_refs=["execution-run://python/1"],
            input_integrity_passed=True,
            model_integrity_passed=True,
            numeric_output_integrity_passed=True,
            result_consistency_report_ref="consistency://incorrect/v1",
            passed=True,
        )


def test_amendments_need_human_approval_and_models_remain_replaceable() -> None:
    model = AnalysisModelSpecification(
        model_spec_id="model-spec-1",
        project_id="project-1",
        model_family="generalized_linear_model",
        outcome_variables=["transfer_score"],
        formula_or_design="transfer_score ~ condition + baseline_score",
        rationale="The specification is replaceable and not hard-coded to LMM.",
    )
    assert model.model_family == "generalized_linear_model"

    change = SubstantiveAnalysisChange(field="model", proposed_value="robust regression")
    with pytest.raises(ValidationError):
        AnalysisPlanAmendment(
            amendment_id="amendment-1",
            project_id="project-1",
            preregistered_plan_ref="prereg-plan://project-1/v1",
            substantive_changes=[change],
            reason="Assumption violation documented before interpretation.",
            created_at=datetime.now(UTC),
            results_viewed=True,
            analysis_label="exploratory",
            status="approved",
        )

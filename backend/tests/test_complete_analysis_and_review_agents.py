"""End-to-end boundary tests for the two completed Phase 1 specialist Agents."""

import pytest
from pydantic import ValidationError

from stem_sci.agents import (
    AgentInput,
    CitationReviewInput,
    CitationReviewItem,
    DataAnalysisAgent,
    DataAnalysisPostExecutionInput,
    DataAnalysisPreAnalysisInput,
    IndependentReviewAgent,
    MethodReviewInput,
    ManuscriptNumericClaim,
    ManuscriptTraceabilityReviewInput,
    PedagogyReviewInput,
    ReviewArbiterInput,
    ReviewCriterion,
    ReproducibilityReviewInput,
)
from stem_sci.core.enums import DecisionScope
from stem_sci.controller.merger import validate_agent_result
from stem_sci.statistics.mode_policy import AnalysisMode
from stem_sci.statistics.models import ExecutionStatus, InterpretationStatus, StatisticalResultCard
from stem_sci.agents.writing_pipeline import AtomicClaimGraph, AtomicClaimNode
from stem_sci.core.claims import ClaimType


def _pre_analysis_input() -> DataAnalysisPreAnalysisInput:
    return DataAnalysisPreAnalysisInput(
        agent_run_id="analysis-agent-complete-1",
        project_id="physics-demo",
        task_ref="physics-demo:pre-analysis",
        study_protocol_ref="protocol://physics-demo/v1",
        preregistered_plan_ref="prereg-plan://physics-demo/v1",
        preregistered_plan_status="frozen",
        preregistration_approval_ref="approval://physics-demo/prereg-v1",
        data_collection_schema_ref="schema://physics-demo/collection-v1",
        variable_dictionary_ref="dictionary://physics-demo/v1",
        analysis_mode=AnalysisMode.PYTHON_ONLY,
        model_specification_refs=["model-spec://physics-demo/main-v1"],
        required_variables=["group", "transfer_score", "prompt_dependency"],
        missingness_checks=["report missingness by group and outcome"],
        range_and_type_checks=["transfer_score is finite numeric"],
        privacy_checks=["reject unredacted direct identifiers"],
        proposed_processing_steps=["apply only approved missing-data handling"],
        missing_data_strategy_ref="prereg-plan://physics-demo/missing-data",
        diagnostic_checks=["check model residuals"],
        robustness_checks=["report the pre-specified sensitivity check"],
    )


def test_data_analysis_agent_returns_typed_pre_and_post_specifications_only() -> None:
    agent = DataAnalysisAgent()
    pre = agent.propose_pre_analysis(_pre_analysis_input())

    assert pre.agent_result.tool_requests == []
    assert pre.readiness_report.status == "READY"
    assert pre.data_audit_specification.required_variables == [
        "group",
        "transfer_score",
        "prompt_dependency",
    ]
    assert pre.data_processing_plan_candidate.requires_human_approval is True
    assert pre.code_specification_draft.required_outputs == [
        "ExecutionRun",
        "ResultValidationReport",
        "StatisticalResultCard",
    ]
    assert pre.code_specification_draft.expected_languages == ["python"]
    assert {artifact.artifact_type for artifact in pre.agent_result.candidate_artifacts} == {
        "AnalysisReadinessReport",
        "CodeSpecificationDraft",
        "DataAuditSpecification",
        "DataProcessingPlanCandidate",
        "ExecutableAnalysisPlanCandidate",
        "ModelDiagnosticRecommendation",
        "RiskFlags",
        "RobustnessCheckPlan",
    }
    assert all("StatisticalResultCardCandidate" not in ref for ref in pre.agent_result.candidate_artifact_refs)

    post = agent.propose_interpretation_boundary(
        DataAnalysisPostExecutionInput(
            agent_run_id="analysis-agent-complete-2",
            project_id="physics-demo",
            task_ref="physics-demo:interpretation",
            statistical_result_card_ref="result-card://physics-demo/v1",
            execution_status=ExecutionStatus.EXECUTION_VERIFIED,
        )
    )
    assert post.agent_result.tool_requests == []
    assert post.agent_result.candidate_artifacts[0].artifact_type == "ResultInterpretationBoundary"
    assert "alter statistical values" in post.interpretation_boundary.prohibited_interpretations[0]
    assert "cross-engine verified" in post.interpretation_boundary.prohibited_interpretations[-1]
    authorized_post = agent.propose_interpretation_boundary_for(
        AgentInput(
            agent_run_id="analysis-agent-complete-2",
            task_ref="physics-demo:interpretation",
            context_bundle_ref="context://physics-demo/analysis",
            allowed_tool_capabilities=[],
            allowed_output_types=["ResultInterpretationBoundary"],
            policy_version="policy-v1",
            prompt_template_version="analysis-v1",
        ),
        DataAnalysisPostExecutionInput(
            agent_run_id="analysis-agent-complete-2",
            project_id="physics-demo",
            task_ref="physics-demo:interpretation",
            statistical_result_card_ref="result-card://physics-demo/v1",
            execution_status=ExecutionStatus.EXECUTION_VERIFIED,
        ),
    )
    assert len(authorized_post.agent_result.candidate_artifacts) == 1


def test_data_analysis_agent_marks_dual_mode_code_specification_for_both_engines() -> None:
    request = _pre_analysis_input().model_copy(update={"analysis_mode": AnalysisMode.SPSS_PYTHON_DUAL})

    outcome = DataAnalysisAgent().propose_pre_analysis(request)

    assert outcome.code_specification_draft.expected_languages == ["spss", "python"]


def test_data_analysis_authorized_entrypoint_omits_ungranted_outputs() -> None:
    agent = DataAnalysisAgent()
    request = _pre_analysis_input()
    outcome = agent.propose_pre_analysis_for(
        AgentInput(
            agent_run_id=request.agent_run_id,
            task_ref=request.task_ref,
            context_bundle_ref="context://physics-demo/analysis",
            allowed_tool_capabilities=[],
            allowed_output_types=["DataAuditSpecification"],
            policy_version="policy-v1",
            prompt_template_version="analysis-v1",
        ),
        request,
    )

    assert [item.artifact_type for item in outcome.agent_result.candidate_artifacts] == [
        "DataAuditSpecification"
    ]
    assert "OUTPUT_CAPABILITY_NOT_GRANTED" in outcome.agent_result.risk_flags


def test_independent_reviewer_citation_method_pedagogy_and_arbiter_are_read_only() -> None:
    reviewer = IndependentReviewAgent()
    citation = reviewer.review_citations(
        CitationReviewInput(
            project_id="physics-demo",
            manuscript_ref="manuscript://physics-demo/v1",
            citations=[
                CitationReviewItem(
                    claim_ref="claim://physics-demo/literature-1",
                    evidence_ref="evidence://physics-demo/1",
                    verification_status="model_generated_unverified",
                    supports_claim=True,
                    context_adequate=True,
                )
            ],
        )
    )
    assert citation.report.overall_recommendation == "MAJOR_REVISION"
    assert citation.findings[0].category == "citation"
    assert citation.findings[0].blocked_target_ids == ["manuscript://physics-demo/v1"]

    method = reviewer.review_method(
        MethodReviewInput(
            project_id="physics-demo",
            protocol_ref="protocol://physics-demo/v1",
            criteria=[
                ReviewCriterion(
                    criterion_id="estimand-alignment",
                    artifact_ref="protocol://physics-demo/v1",
                    category="method",
                    description="Estimand does not align with the allocation mechanism.",
                    passed=False,
                )
            ],
        )
    )
    assert method.revision_requests[0].blocking is True

    pedagogy = reviewer.review_pedagogy(
        PedagogyReviewInput(
            project_id="physics-demo",
            study_protocol_ref="protocol://physics-demo/v1",
            criteria=[
                ReviewCriterion(
                    criterion_id="transfer-task-equivalence",
                    artifact_ref="protocol://physics-demo/v1",
                    category="pedagogy",
                    description="The transfer task repeats the trained task.",
                    passed=False,
                    severity="critical",
                    decision_scope=DecisionScope.STAGE,
                    blocked_target_ids=["stage://analysis"],
                )
            ],
        )
    )
    arbitration = reviewer.arbitrate(
        ReviewArbiterInput(
            project_id="physics-demo",
            reviewed_artifact_ref="manuscript://physics-demo/v1",
            findings=[*citation.findings, *method.findings, *pedagogy.findings],
        )
    )
    assert arbitration.report.overall_recommendation == "BLOCK"
    assert reviewer.capability().allowed_tool_capabilities == []


def test_reproducibility_reviewer_rejects_cross_project_result_cards() -> None:
    card = StatisticalResultCard(
        result_id="foreign-result",
        project_id="another-project",
        execution_run_ref="execution-run://foreign/1",
        analysis_plan_ref="analysis-plan://foreign/1",
        validation_report_ref="validation://foreign/1",
        execution_status=ExecutionStatus.EXECUTION_VERIFIED,
        interpretation_status=InterpretationStatus.PENDING_HUMAN_REVIEW,
        deterministic_parser_version="v1",
        values={"estimate": 1.0},
    )

    with pytest.raises(ValidationError, match="another project's"):
        ReproducibilityReviewInput(
            project_id="physics-demo",
            manuscript_ref="manuscript://physics-demo/1",
            numeric_claims=[
                ManuscriptNumericClaim(
                    claim_ref="claim://physics-demo/1",
                    result_card_ref=card.ref,
                    result_key="estimate",
                    reported_value=1.0,
                )
            ],
            statistical_result_cards=[card],
        )


def test_reviewer_adapts_read_only_outcome_to_candidate_artifacts() -> None:
    reviewer = IndependentReviewAgent()
    outcome = reviewer.review_method(
        MethodReviewInput(
            project_id="physics-demo",
            protocol_ref="protocol://physics-demo/v1",
            criteria=[
                ReviewCriterion(
                    criterion_id="estimand",
                    artifact_ref="protocol://physics-demo/v1",
                    category="method",
                    description="Estimand needs a clearer comparator.",
                    passed=False,
                )
            ],
        )
    )
    result = reviewer.as_agent_result(
        AgentInput(
            agent_run_id="review-agent-result-1",
            task_ref="physics-demo:review",
            context_bundle_ref="context://physics-demo/review",
            allowed_tool_capabilities=[],
            allowed_output_types=list(reviewer.allowed_output_types),
            policy_version="policy-v1",
            prompt_template_version="review-v1",
        ),
        outcome,
    )

    assert {item.artifact_type for item in result.candidate_artifacts} == {
        "ReviewFinding",
        "RevisionRequest",
        "ReviewReport",
    }
    assert result.approval_requests == []
    assert "REVIEW_REQUIRES_CONTROLLER_ROUTE" in result.risk_flags
    assert validate_agent_result(result, reviewer.capability()) is result


def test_traceability_reviewer_derives_a_revision_from_claim_material() -> None:
    outcome = IndependentReviewAgent().review_traceability(
        ManuscriptTraceabilityReviewInput(
            project_id="physics-demo",
            manuscript_ref="manuscript://physics-demo/v1",
            claim_graph=AtomicClaimGraph(
                project_id="physics-demo",
                nodes=[
                    AtomicClaimNode(
                        project_id="physics-demo",
                        claim_id="method-claim-1",
                        text="An unsupported method reference.",
                        claim_type=ClaimType.METHOD,
                        method_ref="protocol://physics-demo/unapproved",
                        section_target="methods",
                    )
                ],
            ),
            approved_study_protocol_refs=["protocol://physics-demo/approved"],
        )
    )

    assert outcome.report.overall_recommendation == "MAJOR_REVISION"
    assert outcome.findings[0].category == "claim_traceability"
    assert outcome.revision_requests[0].artifact_ref == "manuscript://physics-demo/v1"

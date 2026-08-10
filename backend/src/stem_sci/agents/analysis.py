"""Research-computing and data-analysis Agent role boundary.

This role creates analysis *specifications*.  It never mutates a dataset,
freezes data, executes code, or creates an official statistical result card.
Those are Controller-owned calls to deterministic operators.
"""

from datetime import UTC, datetime

from .analysis_contracts import (
    AnalysisReadinessReport,
    CodeSpecificationDraft,
    DataAnalysisInterpretationOutcome,
    DataAnalysisPostExecutionInput,
    DataAnalysisPreAnalysisInput,
    DataAnalysisPreAnalysisOutcome,
    DataAuditSpecification,
    DataProcessingPlanCandidate,
    ExecutableAnalysisPlanCandidate,
    ModelDiagnosticRecommendation,
    ResultInterpretationBoundary,
    RobustnessCheckPlan,
)
from .base import BaseAgent
from .contracts import AgentInput, AgentResult


class DataAnalysisAgent(BaseAgent):
    agent_id = "data_analysis"
    supported_task_types = (
        "pre_analysis",
        "audit_data_specification",
        "draft_analysis_specification",
        "bound_result_interpretation",
    )
    # The Controller, never this Agent, invokes data, coding, and statistics
    # operators from approved specifications.
    allowed_tool_capabilities = ()
    allowed_output_types = (
        "DataAuditSpecification",
        "DataIssueReport",
        "AnalysisReadinessReport",
        "DataProcessingPlanCandidate",
        "ExecutableAnalysisPlanCandidate",
        "CodeSpecificationDraft",
        "ModelDiagnosticRecommendation",
        "RobustnessCheckPlan",
        "ResultInterpretationBoundary",
        "RiskFlags",
    )

    def run(self, agent_input: AgentInput) -> AgentResult:
        """Return specifications only; operators are requested by the Controller."""

        result = super().run(agent_input)
        return result.model_copy(
            update={
                "tool_requests": [],
                "recommendations": [
                    "Controller must validate and human-approve candidate specifications before "
                    "calling any deterministic data, coding, or statistics operator."
                ],
            }
        )

    def run_pre_analysis(self, request: DataAnalysisPreAnalysisInput) -> AgentResult:
        """Propose PRE_ANALYSIS artifacts without inspecting or modifying data."""

        return self.propose_pre_analysis(request).agent_result

    def propose_pre_analysis(
        self, request: DataAnalysisPreAnalysisInput
    ) -> DataAnalysisPreAnalysisOutcome:
        """Build typed specifications that a Controller can gate and store."""

        output_types = (
            "DataAuditSpecification",
            "AnalysisReadinessReport",
            "DataProcessingPlanCandidate",
            "ExecutableAnalysisPlanCandidate",
            "CodeSpecificationDraft",
            "ModelDiagnosticRecommendation",
            "RobustnessCheckPlan",
            "RiskFlags",
        )
        agent_result = AgentResult(
            agent_run_id=request.agent_run_id,
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            candidate_artifact_refs=[
                f"candidate://{self.agent_id}/{request.task_ref}/{output_type}"
                for output_type in output_types
            ],
            recommendations=[
                "Data collection must occur only after the preregistered plan is approved.",
                "Controller must obtain human approval before creating ProcessedDataset or "
                "FrozenDataset.",
                "Controller must compile an ExecutableAnalysisPlan from FrozenDataset schema "
                "without changing preregistered substantive decisions.",
            ],
            confidence=0.5,
            created_at=datetime.now(UTC),
        )
        audit_ref = f"candidate://{self.agent_id}/{request.task_ref}/DataAuditSpecification"
        executable_ref = (
            f"candidate://{self.agent_id}/{request.task_ref}/ExecutableAnalysisPlanCandidate"
        )
        return DataAnalysisPreAnalysisOutcome(
            agent_result=agent_result,
            readiness_report=AnalysisReadinessReport(
                report_id=f"analysis-readiness://{request.agent_run_id}",
                project_id=request.project_id,
                preregistered_plan_ref=request.preregistered_plan_ref,
                status="READY",
                rationale=(
                    "Approved preregistration, study protocol, collection schema, and "
                    "variable dictionary were supplied before data collection."
                ),
            ),
            data_audit_specification=DataAuditSpecification(
                specification_id=f"data-audit-spec://{request.agent_run_id}",
                project_id=request.project_id,
                data_collection_schema_ref=request.data_collection_schema_ref,
                variable_dictionary_ref=request.variable_dictionary_ref,
                required_variables=request.required_variables,
                missingness_checks=request.missingness_checks,
                range_and_type_checks=request.range_and_type_checks,
                privacy_checks=request.privacy_checks,
            ),
            data_processing_plan_candidate=DataProcessingPlanCandidate(
                candidate_id=f"processing-plan-candidate://{request.agent_run_id}",
                project_id=request.project_id,
                data_audit_specification_ref=audit_ref,
                proposed_steps=request.proposed_processing_steps,
                missing_data_strategy_ref=request.missing_data_strategy_ref,
                exclusion_rule_refs=request.exclusion_rule_refs,
            ),
            executable_plan_candidate=ExecutableAnalysisPlanCandidate(
                candidate_id=f"executable-plan-candidate://{request.agent_run_id}",
                project_id=request.project_id,
                preregistered_plan_ref=request.preregistered_plan_ref,
                data_collection_schema_ref=request.data_collection_schema_ref,
                analysis_mode=request.analysis_mode,
                model_specification_refs=request.model_specification_refs,
            ),
            code_specification_draft=CodeSpecificationDraft(
                draft_id=f"code-spec-draft://{request.agent_run_id}",
                project_id=request.project_id,
                executable_plan_candidate_ref=executable_ref,
                expected_dataset_schema_ref=request.data_collection_schema_ref,
                required_outputs=["ExecutionRun", "ResultValidationReport", "StatisticalResultCard"],
            ),
            model_diagnostic_recommendation=ModelDiagnosticRecommendation(
                recommendation_id=f"model-diagnostic://{request.agent_run_id}",
                project_id=request.project_id,
                model_specification_ref=request.model_specification_refs[0],
                diagnostic_checks=request.diagnostic_checks,
                interpretation_limitations=[
                    "Do not make causal claims outside the approved study protocol and estimand."
                ],
            ),
            robustness_check_plan=RobustnessCheckPlan(
                plan_id=f"robustness-plan://{request.agent_run_id}",
                project_id=request.project_id,
                preregistered_plan_ref=request.preregistered_plan_ref,
                planned_checks=request.robustness_checks,
                reporting_rule="Report all pre-specified checks and label any amendment-driven work.",
            ),
        )

    def run_post_execution_interpretation(
        self, request: DataAnalysisPostExecutionInput
    ) -> AgentResult:
        """Propose an interpretation boundary while leaving result values untouched."""

        return self.propose_interpretation_boundary(request).agent_result

    def propose_interpretation_boundary(
        self, request: DataAnalysisPostExecutionInput
    ) -> DataAnalysisInterpretationOutcome:
        """Create a typed post-execution boundary without copying result numbers."""

        agent_result = AgentResult(
            agent_run_id=request.agent_run_id,
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            candidate_artifact_refs=[
                f"candidate://{self.agent_id}/{request.task_ref}/ResultInterpretationBoundary"
            ],
            recommendations=[
                "Interpretation remains pending human review and must cite the immutable "
                "StatisticalResultCard rather than restating or altering its values."
            ],
            confidence=0.5,
            created_at=datetime.now(UTC),
        )
        return DataAnalysisInterpretationOutcome(
            agent_result=agent_result,
            interpretation_boundary=ResultInterpretationBoundary(
                boundary_id=f"interpretation-boundary://{request.agent_run_id}",
                project_id=request.project_id,
                statistical_result_card_ref=request.statistical_result_card_ref,
                execution_status=request.execution_status,
                allowed_interpretations=[
                    "Describe the verified result using the referenced StatisticalResultCard.",
                    "Discuss results only within the approved estimand and protocol boundary.",
                ],
                prohibited_interpretations=[
                    "Do not invent, round, or alter statistical values.",
                    "Do not convert exploratory amendments into confirmatory conclusions.",
                    "Do not make causal claims unsupported by the approved study design.",
                ],
            ),
        )

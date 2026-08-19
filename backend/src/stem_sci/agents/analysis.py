"""Research-computing and data-analysis Agent role boundary."""

from .base import BaseAgent


class DataAnalysisAgent(BaseAgent):
    agent_id = "data_analysis"
    skill_ids = ("data_readiness_audit@v1", "result_card_generation@v1")
    tool_ids = (
        "dataset_schema_profile@v1",
        "data_quality_audit@v1",
        "result_validation_checker@v1",
        "statistical_result_card_builder@v1",
    )
    supported_task_types = ("audit_data", "draft_analysis_specification", "bound_result_interpretation")
    allowed_tool_capabilities = (
        "data_audit",
        "data_processing",
        "data_freeze_request",
        "coding_provider",
        "python_analysis",
        "spss_analysis",
        "result_validation",
    )
    allowed_output_types = (
        "DataIssueReport",
        "AnalysisReadinessReport",
        "DataProcessingPlanCandidate",
        "CodeSpecificationDraft",
        "ModelDiagnosticRecommendation",
        "ResultInterpretationBoundary",
        "StatisticalResultCardCandidate",
        "RiskFlags",
    )

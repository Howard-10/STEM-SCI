"""Research-computing and data-analysis Agent role boundary."""

from .base import BaseAgent


class DataAnalysisAgent(BaseAgent):
    agent_id = "data_analysis"
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

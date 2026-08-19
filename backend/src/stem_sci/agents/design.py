"""Research-design Agent role boundary."""

from .base import BaseAgent


class ResearchDesignAgent(BaseAgent):
    agent_id = "research_design"
    skill_ids = ("research_question_formulation@v1", "protocol_draft_validation@v1")
    tool_ids = ("research_question_validator@v1", "protocol_schema_validator@v1")
    supported_task_types = ("draft_study_protocol", "define_estimand", "draft_preregistration")
    allowed_tool_capabilities = ()
    allowed_output_types = (
        "ResearchQuestionCandidate",
        "HypothesisCandidate",
        "Estimand",
        "CausalDAG",
        "StudyProtocolCandidate",
        "SamplingPlan",
        "InterventionProtocol",
        "ProgrammingTaskSpecification",
        "HintPolicy",
        "CodeRubric",
        "UnitTestSpecification",
        "MeasurementPlan",
        "DataCollectionSchema",
        "PreregisteredAnalysisPlanDraft",
        "QualityGatePlan",
    )

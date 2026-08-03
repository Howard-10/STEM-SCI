"""Research-design Agent role boundary."""

from .base import BaseAgent


class ResearchDesignAgent(BaseAgent):
    agent_id = "research_design"
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

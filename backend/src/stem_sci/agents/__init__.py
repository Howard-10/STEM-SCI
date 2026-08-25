"""Six domain-agent role boundaries for the Phase 1 protocol scaffold."""

from .analysis import DataAnalysisAgent
from .analysis_contracts import (
    DataAnalysisPostExecutionInput,
    DataAnalysisPreAnalysisInput,
    DataAnalysisPhase,
    DataAuditSpecification,
    DataProcessingPlanCandidate,
    ExecutableAnalysisPlanCandidate,
    ResultInterpretationBoundary,
)
from .contracts import (
    AgentCapability,
    AgentInput,
    AgentResult,
    ApprovalRequest,
    CandidateArtifact,
    ReviewFinding,
    ReviewReport,
    RevisionRequest,
    ToolRequest,
)
from .design import ResearchDesignAgent
from .design_contracts import (
    AnalysisPlanDraft,
    MeasurementPlanCandidate,
    ResearchDesignBrief,
    ResearchDesignOutcome,
    StudyProtocolCandidate,
)
from .evidence import EvidenceReviewAgent
from .planner import MentorPlanningAgent
from .planning_contracts import MentorPlanningOutcome, PlanningBrief
from .reviewer import IndependentReviewAgent
from .research_generation import (
    DesignRationaleCandidate,
    MentorPlanningPipeline,
    PlanningRationaleCandidate,
    ResearchDesignPipeline,
)
from .reviewer_contracts import (
    CitationReviewInput,
    CitationReviewItem,
    GeneralReviewOutcome,
    ManuscriptNumericClaim,
    ManuscriptTraceabilityReviewInput,
    MethodReviewInput,
    PedagogyReviewInput,
    ReproducibilityReviewInput,
    ReproducibilityReviewOutcome,
    ReviewPacket,
    ReviewArbiterInput,
    ReviewArbiterOutcome,
    ReviewCriterion,
)
from .writing import PaperWritingAgent

__all__ = [
    "AgentCapability",
    "AgentInput",
    "AgentResult",
    "ApprovalRequest",
    "CitationReviewInput",
    "CitationReviewItem",
    "CandidateArtifact",
    "DataAnalysisAgent",
    "DataAnalysisPhase",
    "DataAnalysisPreAnalysisInput",
    "DataAnalysisPostExecutionInput",
    "DataAuditSpecification",
    "DataProcessingPlanCandidate",
    "DesignRationaleCandidate",
    "ExecutableAnalysisPlanCandidate",
    "EvidenceReviewAgent",
    "AnalysisPlanDraft",
    "IndependentReviewAgent",
    "GeneralReviewOutcome",
    "MentorPlanningAgent",
    "MentorPlanningPipeline",
    "MentorPlanningOutcome",
    "MeasurementPlanCandidate",
    "ManuscriptNumericClaim",
    "ManuscriptTraceabilityReviewInput",
    "MethodReviewInput",
    "PaperWritingAgent",
    "PedagogyReviewInput",
    "ResearchDesignAgent",
    "ResearchDesignBrief",
    "ResearchDesignOutcome",
    "ReproducibilityReviewInput",
    "ReproducibilityReviewOutcome",
    "ReviewPacket",
    "ReviewArbiterInput",
    "ReviewArbiterOutcome",
    "ReviewCriterion",
    "ReviewFinding",
    "ReviewReport",
    "RevisionRequest",
    "ResultInterpretationBoundary",
    "PlanningBrief",
    "PlanningRationaleCandidate",
    "ResearchDesignPipeline",
    "StudyProtocolCandidate",
    "ToolRequest",
]

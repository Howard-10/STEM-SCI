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
    ReviewFinding,
    ReviewReport,
    RevisionRequest,
    ToolRequest,
)
from .design import ResearchDesignAgent
from .evidence import EvidenceReviewAgent
from .planner import MentorPlanningAgent
from .reviewer import IndependentReviewAgent
from .reviewer_contracts import (
    CitationReviewInput,
    CitationReviewItem,
    GeneralReviewOutcome,
    ManuscriptNumericClaim,
    MethodReviewInput,
    PedagogyReviewInput,
    ReproducibilityReviewInput,
    ReproducibilityReviewOutcome,
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
    "DataAnalysisAgent",
    "DataAnalysisPhase",
    "DataAnalysisPreAnalysisInput",
    "DataAnalysisPostExecutionInput",
    "DataAuditSpecification",
    "DataProcessingPlanCandidate",
    "ExecutableAnalysisPlanCandidate",
    "EvidenceReviewAgent",
    "IndependentReviewAgent",
    "GeneralReviewOutcome",
    "MentorPlanningAgent",
    "ManuscriptNumericClaim",
    "MethodReviewInput",
    "PaperWritingAgent",
    "PedagogyReviewInput",
    "ResearchDesignAgent",
    "ReproducibilityReviewInput",
    "ReproducibilityReviewOutcome",
    "ReviewArbiterInput",
    "ReviewArbiterOutcome",
    "ReviewCriterion",
    "ReviewFinding",
    "ReviewReport",
    "RevisionRequest",
    "ResultInterpretationBoundary",
    "ToolRequest",
]

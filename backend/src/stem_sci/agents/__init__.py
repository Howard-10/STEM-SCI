"""Six domain-agent role boundaries for the Phase 1 protocol scaffold."""

from .analysis import DataAnalysisAgent
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
from .evidence import EvidenceReviewAgent
from .planner import MentorPlanningAgent
from .reviewer import IndependentReviewAgent
from .writing import PaperWritingAgent

__all__ = [
    "AgentCapability",
    "AgentInput",
    "AgentResult",
    "ApprovalRequest",
    "CandidateArtifact",
    "DataAnalysisAgent",
    "EvidenceReviewAgent",
    "IndependentReviewAgent",
    "MentorPlanningAgent",
    "PaperWritingAgent",
    "ResearchDesignAgent",
    "ReviewFinding",
    "ReviewReport",
    "RevisionRequest",
    "ToolRequest",
]

"""Evidence-review Agent role boundary."""

from .base import BaseAgent


class EvidenceReviewAgent(BaseAgent):
    agent_id = "evidence_review"
    supported_task_types = ("design_search_protocol", "screen_evidence", "synthesize_evidence")
    allowed_tool_capabilities = (
        "literature_search",
        "paper_screening",
        "paper_extraction",
        "source_verification",
    )
    allowed_output_types = (
        "SearchProtocolCandidate",
        "InclusionExclusionCriteria",
        "PaperCardCollection",
        "EvidenceMatrixCandidate",
        "EvidenceConflictMap",
        "ResearchGapReport",
        "EvidenceSufficiencyReport",
        "LiteratureNeedUpdate",
    )

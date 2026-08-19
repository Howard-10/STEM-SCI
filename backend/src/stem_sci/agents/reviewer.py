"""Independent-review Agent role boundary."""

from .base import BaseAgent


class IndependentReviewAgent(BaseAgent):
    agent_id = "independent_review"
    skill_ids = (
        "citation_review@v1",
        "methodology_review@v1",
        "reproducibility_review@v1",
    )
    tool_ids = (
        "citation_audit@v1",
        "evidence_reference_audit@v1",
        "method_protocol_alignment_checker@v1",
        "statistical_claim_audit@v1",
        "reproducibility_artifact_audit@v1",
        "bilingual_draft_audit@v1",
    )
    supported_task_types = ("review_citations", "review_method", "review_reproducibility")
    allowed_tool_capabilities = tool_ids
    allowed_output_types = ("ReviewFinding", "RevisionRequest", "ReviewReport", "OverallRecommendation")

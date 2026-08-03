"""Independent-review Agent role boundary."""

from .base import BaseAgent


class IndependentReviewAgent(BaseAgent):
    agent_id = "independent_review"
    supported_task_types = ("review_citations", "review_method", "review_reproducibility")
    allowed_tool_capabilities = ()
    allowed_output_types = ("ReviewFinding", "RevisionRequest", "ReviewReport", "OverallRecommendation")

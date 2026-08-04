"""Evidence-review Agent role boundary."""

from stem_sci.context.models import ContextBundle

from .base import BaseAgent
from .contracts import AgentInput, AgentResult


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

    def run_with_context(self, agent_input: AgentInput, context: ContextBundle) -> AgentResult:
        """Create evidence candidates while preserving source references from Context MVP."""
        result = self.run(agent_input)
        risk_flags = list(result.risk_flags)
        unresolved_questions = [*result.unresolved_questions, *context.unresolved_questions]
        if not context.evidence_refs:
            risk_flags.append("INSUFFICIENT_VERIFIED_EVIDENCE")
        return result.model_copy(
            update={
                "evidence_refs": [evidence.evidence_id for evidence in context.evidence_refs],
                "risk_flags": list(dict.fromkeys([*risk_flags, *context.risk_flags])),
                "unresolved_questions": list(dict.fromkeys(unresolved_questions)),
                "recommendations": [
                    *result.recommendations,
                    "Source evidence must be verified before supporting a formal claim.",
                ],
            }
        )

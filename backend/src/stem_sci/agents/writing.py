"""Paper-writing Agent role boundary."""

from .base import BaseAgent


class PaperWritingAgent(BaseAgent):
    agent_id = "paper_writing"
    supported_task_types = ("draft_manuscript", "map_claims_to_evidence", "draft_reproducibility_statement")
    allowed_tool_capabilities = ()
    allowed_output_types = (
        "AtomicClaimCandidate",
        "ClaimEvidenceMap",
        "ManuscriptOutline",
        "ManuscriptDraft",
        "AbstractDraft",
        "TableFigureNarrative",
        "LimitationsDraft",
        "ReproducibilityStatement",
    )

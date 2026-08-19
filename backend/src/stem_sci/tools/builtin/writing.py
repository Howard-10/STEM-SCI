"""Candidate-only manuscript and claim validation adapters."""
from __future__ import annotations

from typing import Any

from stem_sci.tools.models import ToolRunStatus

from .common import BuiltinResult, blocked


class _WritingTool:
    def __init__(self, name: str, output: str): self.tool_id, self.output = name, output
    def execute(self, project_id: str, **kwargs: Any) -> BuiltinResult[Any]:
        if not project_id: return blocked("INVALID_INPUT")
        return BuiltinResult(value={"project_id": project_id, "output_type": self.output, "candidate": True, **kwargs}, status=ToolRunStatus.SUCCEEDED)

_NAMES = {
    "writing_context_resolver":"WritingContextBundle", "atomic_claim_validator":"ValidationReport", "claim_evidence_mapper":"ClaimEvidenceMap", "manuscript_outline_validator":"ValidationReport", "manuscript_renderer_zh":"ManuscriptDraft", "manuscript_renderer_en":"ManuscriptDraft", "bilingual_consistency_checker":"BilingualConsistencyReport", "citation_consistency_checker":"ValidationReport", "numeric_literal_checker":"ValidationReport", "result_strength_checker":"ValidationReport", "limitation_coverage_checker":"ValidationReport", "reproducibility_statement_builder":"ReproducibilityStatement", "table_figure_narrative_builder":"TableFigureNarrative"
}
globals().update({name: _WritingTool(name, output) for name, output in _NAMES.items()})
__all__ = list(_NAMES)

"""Read-only review finding and revision proposal adapters."""
from __future__ import annotations

from typing import Any

from stem_sci.tools.models import ToolRunStatus

from .common import BuiltinResult, blocked


class _ReviewTool:
    def __init__(self, name: str, output: str): self.tool_id, self.output = name, output
    def execute(self, project_id: str, **kwargs: Any) -> BuiltinResult[Any]:
        if not project_id: return blocked("INVALID_INPUT")
        return BuiltinResult(value={"project_id": project_id, "output_type": self.output, "proposal_only": True, **kwargs}, status=ToolRunStatus.SUCCEEDED)

_NAMES = {"citation_audit":"ReviewFindingSet", "evidence_reference_audit":"ReviewFindingSet", "method_protocol_alignment_checker":"ReviewFindingSet", "statistical_claim_audit":"ReviewFindingSet", "result_limitation_audit":"ReviewFindingSet", "reproducibility_artifact_audit":"ReviewFindingSet", "bilingual_draft_audit":"ReviewFindingSet", "review_finding_builder":"ReviewReport", "revision_request_builder":"RevisionRequest", "review_summary_builder":"ReviewReport"}
globals().update({name: _ReviewTool(name, output) for name, output in _NAMES.items()})
__all__ = list(_NAMES)

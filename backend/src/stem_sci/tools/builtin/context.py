"""Project-scoped context and evidence reference Tools."""

from __future__ import annotations

from typing import Any

from stem_sci.context.models import ContextBundle, EvidenceRef
from stem_sci.context.service import ContextNotFoundError, ContextService
from stem_sci.tools.policies import ToolPolicyError

from .common import BuiltinResult, execute_wrapped


class ContextBundleReadTool:
    tool_id = "context_bundle_read"

    def __init__(self, provider: ContextService) -> None:
        self.provider = provider

    def execute(self, project_id: str, context_id: str) -> BuiltinResult[Any]:
        def read() -> ContextBundle:
            try:
                bundle = self.provider.get_bundle(project_id, context_id)
            except ContextNotFoundError:
                owner = self.provider.bundle_project(context_id)
                if owner is not None and owner != project_id:
                    raise ToolPolicyError("PROJECT_SCOPE_VIOLATION") from None
                raise
            if bundle.project_id != project_id:
                raise ToolPolicyError("PROJECT_SCOPE_VIOLATION")
            return bundle

        return execute_wrapped(read)


class EvidenceRefValidateTool:
    tool_id = "evidence_ref_validate"

    def __init__(self, provider: ContextService) -> None:
        self.provider = provider

    def execute(self, project_id: str, evidence_id: str) -> BuiltinResult[Any]:
        def read() -> EvidenceRef:
            try:
                detail = self.provider.get_evidence(project_id, evidence_id)
            except ContextNotFoundError:
                owner = self.provider.evidence_project(evidence_id)
                if owner is not None and owner != project_id:
                    raise ToolPolicyError("PROJECT_SCOPE_VIOLATION") from None
                raise
            if detail.project_id != project_id:
                raise ToolPolicyError("PROJECT_SCOPE_VIOLATION")
            return EvidenceRef(**detail.model_dump(exclude={"relation", "verification_note", "verified_by", "verified_at"}))

        return execute_wrapped(read)


context_bundle_read: ContextBundleReadTool | None = None
evidence_ref_validate: EvidenceRefValidateTool | None = None


__all__ = ["ContextBundleReadTool", "EvidenceRefValidateTool", "context_bundle_read", "evidence_ref_validate"]

"""Deterministic validation for evidence pipeline inputs."""

from __future__ import annotations

from .models import EvidenceReviewContext


def validate_evidence_context(context: EvidenceReviewContext) -> EvidenceReviewContext:
    allowed = set(context.allowed_verification_statuses)
    source_refs = set(context.source_refs)
    for evidence in context.evidence_refs:
        if evidence.project_id != context.project_id:
            raise ValueError("evidence project does not match context project")
        if evidence.verification_status not in allowed:
            raise ValueError("evidence must use an allowed verified status")
        if evidence.source_id not in source_refs:
            raise ValueError("evidence source is absent from context source refs")
    return context

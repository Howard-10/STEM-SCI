"""Controller-facing context provider over the existing local Context MVP."""

from __future__ import annotations

from typing import Protocol

from .models import (
    ContextBuildRequest,
    ContextBundle,
    EvidenceDetail,
    EvidenceSearchRequest,
    EvidenceSearchResult,
    SourceChunk,
    VerificationStatus,
)
from .service import ContextService


class ContextProvider(Protocol):
    def build_context(
        self,
        project_id: str,
        task_ref: str,
        query: str,
        token_budget: int,
    ) -> ContextBundle: ...

    def get_bundle(self, project_id: str, context_id: str) -> ContextBundle: ...

    def get_evidence(self, project_id: str, evidence_id: str) -> EvidenceDetail: ...

    def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]: ...

    def chunks(self, project_id: str, source_id: str) -> list[SourceChunk]: ...


class LocalContextProvider:
    """Use local SQLite evidence until a GraphRAG provider is introduced."""

    def __init__(self, service: ContextService) -> None:
        self.service = service

    def build_context(
        self,
        project_id: str,
        task_ref: str,
        query: str,
        token_budget: int,
    ) -> ContextBundle:
        return self.service.build(
            ContextBuildRequest(
                project_id=project_id,
                task_ref=task_ref,
                query=query,
                token_budget=token_budget,
                allowed_verification_statuses=[
                    VerificationStatus.SOURCE_VERIFIED,
                    VerificationStatus.HUMAN_VERIFIED,
                    VerificationStatus.DEMO_SEED,
                ],
            )
        )

    def get_bundle(self, project_id: str, context_id: str) -> ContextBundle:
        return self.service.get_bundle(project_id, context_id)

    def get_evidence(self, project_id: str, evidence_id: str) -> EvidenceDetail:
        return self.service.get_evidence(project_id, evidence_id)

    def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        return self.service.search(request)

    def chunks(self, project_id: str, source_id: str) -> list[SourceChunk]:
        return self.service.chunks(project_id, source_id)

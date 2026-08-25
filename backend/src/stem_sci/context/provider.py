"""Controller-facing context provider over the existing local Context MVP."""

from __future__ import annotations

from typing import Protocol

from .models import ContextBuildRequest, ContextBundle, VerificationStatus
from .service import ContextService


class ContextProvider(Protocol):
    def build_context(
        self,
        project_id: str,
        task_ref: str,
        query: str,
        token_budget: int,
    ) -> ContextBundle: ...


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


class HybridContextProvider:
    """Controller adapter for the read-only shared Physics-STEM corpus.

    The provider uses formal mode because Controller-facing Agent contexts must
    not silently include unverified graph triples or unresolved excerpts.
    """

    def __init__(self, knowledge_service: "HybridKnowledgeService") -> None:
        self.knowledge_service = knowledge_service

    def build_context(
        self,
        project_id: str,
        task_ref: str,
        query: str,
        token_budget: int,
    ) -> ContextBundle:
        return self.knowledge_service.build_context(
            project_id=project_id,
            task_ref=task_ref,
            query=query,
            token_budget=token_budget,
            mode="formal",
        )


from stem_sci.knowledge.service import HybridKnowledgeService  # noqa: E402  # isort: skip

"""Runtime handlers for the literature-facing workflow operators."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, cast

from pydantic import JsonValue

from stem_sci.artifacts.artifact_store import ArtifactStore, InMemoryArtifactStore
from stem_sci.artifacts.content_store import (
    ArtifactContent,
    ArtifactContentStore,
    InMemoryArtifactContentStore,
)
from stem_sci.artifacts.models import ArtifactRef
from stem_sci.context.models import ContextBundle, VerificationStatus
from stem_sci.core.enums import RunStatus
from stem_sci.knowledge.models import ContextMode, RetrievalSearchRequest
from stem_sci.knowledge.service import HybridKnowledgeService

@dataclass(frozen=True)
class OperatorExecutionContext:
    """Controller-supplied context for one operator invocation."""

    project_id: str
    agent_run_id: str
    query: str
    context_bundle: ContextBundle | None = None


@dataclass(frozen=True)
class OperatorExecutionOutcome:
    """Execution result returned by a concrete operator handler."""

    status: RunStatus
    output_artifact_refs: list[str]
    error_ref: str | None = None


OperatorHandler = Callable[
    [str, Any, OperatorExecutionContext, str], OperatorExecutionOutcome
]


class KnowledgeOperatorRuntime:
    """Concrete literature operators backed by the shared knowledge service.

    These operators are intentionally bounded: they can search and organize
    corpus material, but they cannot approve research state or claim source
    verification without a locator-capable corpus.
    """

    def __init__(
        self,
        knowledge_service: HybridKnowledgeService,
        *,
        artifact_store: ArtifactStore | None = None,
        artifact_content_store: ArtifactContentStore | None = None,
    ) -> None:
        self.knowledge_service = knowledge_service
        self.artifact_store = artifact_store or InMemoryArtifactStore()
        self.artifact_content_store = (
            artifact_content_store or InMemoryArtifactContentStore()
        )

    def handlers(self) -> dict[str, OperatorHandler]:
        return {
            "literature_search": self.literature_search,
            "paper_screening": self.paper_screening,
            "paper_extraction": self.paper_extraction,
            "source_verification": self.source_verification,
        }

    def literature_search(
        self,
        project_id: str,
        request: Any,
        context: OperatorExecutionContext,
        operator_run_id: str,
    ) -> OperatorExecutionOutcome:
        query = context.query.strip()
        if not query:
            return self._failed("missing_query")
        response = self.knowledge_service.search(
            RetrievalSearchRequest(
                project_id=project_id,
                corpus_ids=["physics_stem_v1"],
                query=query,
                mode=ContextMode.DISCOVERY,
                limit=12,
            )
        )
        body = {
            "project_id": project_id,
            "query": query,
            "corpus_id": response.corpus_id,
            "retrieval_status": response.retrieval_status,
            "risk_flags": response.risk_flags,
            "manifest_refs": response.manifest_refs,
            "candidate_papers": [
                item.model_dump(mode="json") for item in response.candidate_papers
            ],
            "chunk_hits": [
                item.model_dump(mode="json") for item in response.chunk_hits
            ],
        }
        ref = self._persist(
            project_id,
            operator_run_id,
            "EvidenceSet",
            body,
            created_by="literature_search",
        )
        return OperatorExecutionOutcome(
            status=RunStatus.SUCCEEDED if response.chunk_hits else RunStatus.NEEDS_REVIEW,
            output_artifact_refs=[ref],
            error_ref=None if response.chunk_hits else "error://literature_search/no_hits",
        )

    def paper_screening(
        self,
        project_id: str,
        request: Any,
        context: OperatorExecutionContext,
        operator_run_id: str,
    ) -> OperatorExecutionOutcome:
        evidence = self._evidence_items(context)
        body = {
            "project_id": project_id,
            "query": context.query,
            "decision": "INCLUDE" if evidence else "UNCERTAIN",
            "reason": (
                "Bounded corpus evidence was supplied by the Controller."
                if evidence
                else "No bounded evidence was supplied for screening."
            ),
            "evidence_refs": [item["evidence_id"] for item in evidence],
            "source_refs": sorted({item["source_id"] for item in evidence}),
        }
        ref = self._persist(
            project_id,
            operator_run_id,
            "ScreenedPaperSet",
            body,
            created_by="paper_screening",
        )
        return OperatorExecutionOutcome(
            status=RunStatus.SUCCEEDED if evidence else RunStatus.NEEDS_REVIEW,
            output_artifact_refs=[ref],
        )

    def paper_extraction(
        self,
        project_id: str,
        request: Any,
        context: OperatorExecutionContext,
        operator_run_id: str,
    ) -> OperatorExecutionOutcome:
        evidence = self._evidence_items(context)
        cards: dict[str, dict[str, Any]] = {}
        for item in evidence:
            source_id = str(item["source_id"])
            card = cards.setdefault(
                source_id,
                {
                    "paper_card_id": f"{project_id}:{source_id}:card",
                    "project_id": project_id,
                    "source_ref": source_id,
                    "title": source_id,
                    "main_findings": [],
                    "limitations": [
                        "Operator extraction preserves retrieved excerpts; semantic extraction requires review."
                    ],
                    "evidence_refs": [],
                },
            )
            card["main_findings"].append(item["excerpt"])
            card["evidence_refs"].append(item["evidence_id"])
        body = {
            "project_id": project_id,
            "query": context.query,
            "cards": list(cards.values()),
        }
        ref = self._persist(
            project_id,
            operator_run_id,
            "PaperCard",
            body,
            created_by="paper_extraction",
        )
        return OperatorExecutionOutcome(
            status=RunStatus.SUCCEEDED if cards else RunStatus.NEEDS_REVIEW,
            output_artifact_refs=[ref],
        )

    def source_verification(
        self,
        project_id: str,
        request: Any,
        context: OperatorExecutionContext,
        operator_run_id: str,
    ) -> OperatorExecutionOutcome:
        evidence = self._evidence_items(context)
        formal_ready = (
            self.knowledge_service.readiness("physics_stem_v1").formal_evidence_ready
            and bool(evidence)
            and all(
                item["verification_status"]
                in {
                    VerificationStatus.SOURCE_VERIFIED.value,
                    VerificationStatus.HUMAN_VERIFIED.value,
                }
                for item in evidence
            )
        )
        output_status = (
            VerificationStatus.SOURCE_VERIFIED.value
            if formal_ready
            else VerificationStatus.MODEL_GENERATED_UNVERIFIED.value
        )
        body = {
            "project_id": project_id,
            "verification_status": output_status,
            "verification_mode": "locator_index" if formal_ready else "development_traceability",
            "verified": formal_ready,
            "evidence_refs": [
                {
                    **item,
                    "verification_status": output_status,
                }
                for item in evidence
            ],
            "risk_flags": (
                []
                if formal_ready
                else ["formal_locator_index_unavailable", "SOURCE_REVIEW_REQUIRED"]
            ),
        }
        ref = self._persist(
            project_id,
            operator_run_id,
            "VerifiedEvidenceRef",
            body,
            created_by="source_verification",
        )
        return OperatorExecutionOutcome(
            status=RunStatus.SUCCEEDED if formal_ready and evidence else RunStatus.NEEDS_REVIEW,
            output_artifact_refs=[ref],
            error_ref=(
                None
                if formal_ready and evidence
                else "error://source_verification/review_required"
            ),
        )

    @staticmethod
    def _failed(reason: str) -> OperatorExecutionOutcome:
        return OperatorExecutionOutcome(
            status=RunStatus.FAILED,
            output_artifact_refs=[],
            error_ref=f"error://knowledge_operator/{reason}",
        )

    @staticmethod
    def _evidence_items(context: OperatorExecutionContext) -> list[dict[str, Any]]:
        if context.context_bundle is None:
            return []
        return [
            {
                "evidence_id": item.evidence_id,
                "source_id": item.source_id,
                "chunk_id": item.chunk_id,
                "canonical_chunk_id": item.canonical_chunk_id,
                "canonical_paper_id": item.canonical_paper_id,
                "pdf_relative_path": item.pdf_relative_path,
                "excerpt": item.excerpt,
                "verification_status": item.verification_status.value,
            }
            for item in context.context_bundle.evidence_refs
        ]

    def _persist(
        self,
        project_id: str,
        operator_run_id: str,
        artifact_type: str,
        body: dict[str, Any],
        *,
        created_by: str,
    ) -> str:
        artifact_id = f"{operator_run_id}:artifact:0"
        content = self.artifact_content_store.put(
            ArtifactContent(
                project_id=project_id,
                artifact_id=artifact_id,
                version=1,
                artifact_type=artifact_type,
                schema_version="v1",
                body=cast(dict[str, JsonValue], body),
                created_at=datetime.now(UTC),
            )
        )
        if content.content_hash is None:
            raise ValueError("operator artifact content has no hash")
        content_uri = f"artifact-content://{project_id}/{artifact_id}/1"
        self.artifact_store.put(
            ArtifactRef(
                artifact_id=artifact_id,
                project_id=project_id,
                artifact_type=artifact_type,
                version=1,
                content_uri=content_uri,
                sha256=content.content_hash,
                created_at=content.created_at,
                created_by=created_by,
            )
        )
        return content_uri

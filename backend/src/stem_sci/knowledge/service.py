"""Shared-corpus search and ContextBundle assembly, isolated from Agent logic."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Literal

from neo4j.exceptions import Neo4jError, ServiceUnavailable
from uuid import uuid4

from stem_sci.context.models import ContextBundle, EvidenceRef, SourceLocation, VerificationStatus
from stem_sci.context.service import ContextService

from .graph_retriever import GraphRetriever
from .hybrid_retriever import HybridRetriever
from .identity import PaperIdentityResolver
from .manifest import CorpusRegistry
from .neo4j_graph_retriever import Neo4jGraphRetriever
from .models import (
    ContextMode,
    CorpusManifest,
    CorpusReadiness,
    HybridContextBuildRequest,
    RetrievalHit,
    RetrievalHitSummary,
    RetrievalMode,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
)
from .retrievers import DenseRetriever, LocalMetadataCorpus, SparseRetriever


def _now() -> str:
    return datetime.now(UTC).isoformat()


class HybridKnowledgeService:
    """Build discovery or formal ContextBundles from declared, read-only assets."""

    def __init__(self, context_service: ContextService, registry: CorpusRegistry | None = None) -> None:
        self._context_service = context_service
        self._registry = registry or CorpusRegistry()
        self._graph_cache: dict[str, object] = {}

    def list_corpora(self) -> list[CorpusManifest]:
        """Return public manifest metadata; raw source paths remain local-only."""

        return [self._registry.load_manifest("physics_stem_v1")]

    def manifest(self, corpus_id: str) -> CorpusManifest:
        """Return one declared corpus manifest."""

        return self._registry.load_manifest(corpus_id)

    def readiness(self, corpus_id: str) -> "CorpusReadiness":
        """Expose the safe readiness summary without leaking local asset paths."""

        return self._registry.readiness(corpus_id)

    def search(self, request: RetrievalSearchRequest) -> RetrievalSearchResponse:
        """Search one approved shared corpus with explicit formal/discovery behavior."""

        if request.corpus_ids != ["physics_stem_v1"]:
            raise ValueError("Only the read-only physics_stem_v1 shared corpus is available")
        manifest = self._registry.load_manifest("physics_stem_v1")
        readiness = self._registry.readiness(manifest.corpus_id)
        manifest_refs = self._manifest_refs(manifest)
        if request.mode is ContextMode.FORMAL and not readiness.formal_evidence_ready:
            return self._unavailable(request, manifest, manifest_refs, readiness.risk_flags)
        if request.mode is ContextMode.DISCOVERY and not readiness.discovery_ready:
            return self._unavailable(request, manifest, manifest_refs, readiness.risk_flags)

        resolver = PaperIdentityResolver.from_catalog_path(
            self._registry.asset_path(manifest.identity_map)
        )
        corpus = LocalMetadataCorpus.from_metadata_path(
            self._registry.asset_path(manifest.vector_metadata), resolver
        )
        graph, graph_issue = self._graph_retriever(manifest, resolver)
        sparse = SparseRetriever(corpus)
        dense = DenseRetriever(corpus, self._registry.asset_path(manifest.vector_index))
        retriever = HybridRetriever(
            corpus_id=manifest.corpus_id,
            manifest_refs=manifest_refs,
            graph_retriever=graph,
            dense_search=dense.search,
            sparse_search=sparse.search,
        )
        hits, trace = retriever.retrieve(request.query, limit=request.limit)
        if graph_issue is not None:
            trace = trace.model_copy(
                update={"risk_flags": [*trace.risk_flags, graph_issue], "graph_available": False}
            )
        strict_full_chain = (
            os.getenv("STEM_SCI_REQUIRE_FULL_CHAIN", "false").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        if strict_full_chain:
            strict_issue = HybridRetriever.strict_failure(trace)
            if strict_issue is not None:
                trace = trace.model_copy(
                    update={"risk_flags": [*trace.risk_flags, strict_issue]}
                )
                return self._unavailable(
                    request,
                    manifest,
                    manifest_refs,
                    sorted(set([*readiness.risk_flags, *trace.risk_flags])),
                    trace=trace,
                )
        status: Literal["READY", "DEGRADED", "UNAVAILABLE"] = (
            "READY" if trace.retrieval_mode is RetrievalMode.HYBRID_GRAPH_GUIDED else "DEGRADED"
        )
        if trace.retrieval_mode is RetrievalMode.UNAVAILABLE:
            status = "UNAVAILABLE"
        readiness_risks = readiness.risk_flags
        if request.mode is ContextMode.DISCOVERY:
            readiness_risks = [risk for risk in readiness_risks if not risk.startswith("formal_")]
        risk_flags = sorted(set([*readiness_risks, *trace.risk_flags]))
        navigated_paper_ids = {
            candidate.canonical_paper_id for candidate in trace.graph_candidates
        }
        return RetrievalSearchResponse(
            project_id=request.project_id,
            corpus_id=manifest.corpus_id,
            requested_mode=request.mode,
            retrieval_status=status,
            degraded_mode=(None if status == "READY" else trace.retrieval_mode),
            candidate_papers=trace.graph_candidates,
            chunk_hits=[
                self._summary(
                    hit,
                    locator_status="UNRESOLVED",
                    graph_navigated=hit.canonical_paper_id in navigated_paper_ids,
                )
                for hit in hits
            ],
            retrieval_trace=trace,
            risk_flags=risk_flags,
            manifest_refs=manifest_refs,
        )

    def _graph_retriever(
        self,
        manifest: CorpusManifest,
        resolver: PaperIdentityResolver,
    ) -> tuple[object | None, str | None]:
        """Prefer Neo4j when configured, with JSON navigation as an explicit fallback."""

        backend = os.getenv("STEM_SCI_GRAPH_BACKEND", "auto").strip().lower()
        if backend in {"neo4j", "auto"}:
            try:
                cache_key = "|".join(
                    [
                        os.getenv("NEO4J_URI", "bolt://localhost:7688"),
                        os.getenv("NEO4J_USERNAME", "neo4j"),
                        os.getenv("NEO4J_DATABASE", "neo4j"),
                        os.getenv("NEO4J_PROJECT_ID", "stem-sci"),
                    ]
                )
                cached = self._graph_cache.get(cache_key)
                if cached is not None:
                    return cached, None
                retriever = Neo4jGraphRetriever(resolver)
                self._graph_cache[cache_key] = retriever
                return retriever, None
            except (
                OSError,
                RuntimeError,
                ValueError,
                Neo4jError,
                ServiceUnavailable,
            ) as error:
                if backend == "neo4j":
                    return None, f"neo4j_graph_unavailable:{type(error).__name__}"
        try:
            return GraphRetriever(self._registry.asset_path(manifest.graph_artifact), resolver), None
        except (OSError, ValueError) as error:
            return None, f"json_graph_unavailable:{type(error).__name__}"

    def build_context(
        self,
        *,
        project_id: str,
        task_ref: str,
        query: str,
        token_budget: int,
        mode: str = "discovery",
    ) -> ContextBundle:
        """Assemble and persist a bounded ContextBundle from retrieval hits.

        Formal mode intentionally fails closed until a page/character locator
        index is supplied and verified by the corpus manifest.
        """

        context_mode = ContextMode(mode)
        response = self.search(
            RetrievalSearchRequest(
                project_id=project_id,
                corpus_ids=["physics_stem_v1"],
                query=query,
                mode=context_mode,
                limit=20,
            )
        )
        selected: list[EvidenceRef] = []
        tokens_used = 0
        for hit in response.chunk_hits:
            cost = max(1, len(hit.excerpt) // 4)
            if tokens_used + cost > token_budget:
                continue
            evidence_id = self._evidence_id(project_id, response.corpus_id, hit.canonical_chunk_id)
            selected.append(
                EvidenceRef(
                    evidence_id=evidence_id,
                    project_id=project_id,
                    source_id=f"shared:{response.corpus_id}:{hit.canonical_paper_id}",
                    chunk_id=hit.canonical_chunk_id,
                    excerpt=hit.excerpt,
                    location=SourceLocation(
                        chunk_index=hit.chunk_index,
                        char_start=0,
                        char_end=len(hit.excerpt),
                        heading=hit.section_hint,
                    ),
                    verification_status=VerificationStatus.MODEL_GENERATED_UNVERIFIED,
                    corpus_id=response.corpus_id,
                    canonical_paper_id=hit.canonical_paper_id,
                    canonical_chunk_id=hit.canonical_chunk_id,
                    retrieval_modalities=[str(modality) for modality in hit.retrieval_modalities],
                )
            )
            tokens_used += cost
        if context_mode is ContextMode.FORMAL:
            # Defensive invariant: no formal bundle may contain unverified shared evidence.
            selected = []
            tokens_used = 0
        risk_flags = list(response.risk_flags)
        if not selected:
            risk_flags.append("insufficient_verified_evidence")
        canonical = {
            "project_id": project_id,
            "task_ref": task_ref,
            "query": response.retrieval_trace.query_normalized,
            "mode": context_mode.value,
            "manifest_refs": response.manifest_refs,
            "evidence": [
                {
                    "id": ref.evidence_id,
                    "chunk": ref.canonical_chunk_id,
                    "status": ref.verification_status.value,
                    "excerpt_hash": hashlib.sha256(ref.excerpt.encode("utf-8")).hexdigest(),
                }
                for ref in selected
            ],
        }
        bundle = ContextBundle(
            context_id=f"ctx_{uuid4().hex}",
            project_id=project_id,
            task_ref=task_ref,
            query=query,
            evidence_refs=selected,
            source_refs=sorted({ref.source_id for ref in selected}),
            unresolved_questions=([] if selected else ["No eligible traceable evidence matched the request"]),
            risk_flags=([] if selected else ["insufficient_verified_evidence"]),
            verification_summary={
                status.value: sum(ref.verification_status is status for ref in selected)
                for status in VerificationStatus
            },
            token_budget=token_budget,
            estimated_tokens=tokens_used,
            context_hash=hashlib.sha256(
                json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            generated_at=_now(),
            context_mode=context_mode.value,
            corpus_refs=[response.corpus_id],
            retrieval_strategy="hybrid",
            retrieval_trace_ref=(
                f"retrieval://{response.corpus_id}/{hashlib.sha256(response.retrieval_trace.query_normalized.encode('utf-8')).hexdigest()[:16]}"
            ),
            retrieval_risk_flags=sorted(set(risk_flags)),
            manifest_refs=response.manifest_refs,
        )
        return self._context_service.persist_bundle(bundle)

    def build_from_request(self, request: HybridContextBuildRequest) -> ContextBundle:
        """Build a bundle from the public API contract."""

        return self.build_context(
            project_id=request.project_id,
            task_ref=request.task_ref,
            query=request.query,
            token_budget=request.token_budget,
            mode=request.mode.value,
        )

    @staticmethod
    def _manifest_refs(manifest: CorpusManifest) -> list[str]:
        return [
            f"manifest:{manifest.corpus_id}:{manifest.corpus_version}",
            f"sha256:{manifest.identity_map.sha256}",
            f"sha256:{manifest.graph_artifact.sha256}",
            f"sha256:{manifest.vector_metadata.sha256}",
            f"sha256:{manifest.vector_index.sha256}",
        ]

    @staticmethod
    def _evidence_id(project_id: str, corpus_id: str, canonical_chunk_id: str) -> str:
        value = "\x00".join([project_id, corpus_id, canonical_chunk_id])
        return f"shared_evd_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"

    @staticmethod
    def _modalities(
        hit: RetrievalHit,
        *,
        graph_navigated: bool,
    ) -> list[Literal["dense", "sparse", "graph_navigation"]]:
        modalities: list[Literal["dense", "sparse", "graph_navigation"]] = []
        if graph_navigated:
            modalities.append("graph_navigation")
        if hit.dense_rank is not None:
            modalities.append("dense")
        if hit.sparse_rank is not None:
            modalities.append("sparse")
        return modalities

    @staticmethod
    def _summary(
        hit: RetrievalHit,
        *,
        locator_status: Literal["RESOLVED", "UNRESOLVED"],
        graph_navigated: bool,
    ) -> RetrievalHitSummary:
        excerpt = " ".join(hit.text.split())[:800]
        return RetrievalHitSummary(
            canonical_chunk_id=hit.canonical_chunk_id,
            canonical_paper_id=hit.canonical_paper_id,
            source_filename=hit.source_filename,
            paper_title=hit.paper_title,
            normalized_doi=hit.normalized_doi,
            chunk_index=hit.chunk_index,
            section_hint=hit.section_hint,
            excerpt=excerpt,
            dense_rank=hit.dense_rank,
            sparse_rank=hit.sparse_rank,
            rrf_score=hit.rrf_score,
            locator_status=locator_status,
            retrieval_modalities=HybridKnowledgeService._modalities(
                hit,
                graph_navigated=graph_navigated,
            ),
        )

    @staticmethod
    def _unavailable(
        request: RetrievalSearchRequest,
        manifest: CorpusManifest,
        manifest_refs: list[str],
        risks: list[str],
        trace=None,
    ) -> RetrievalSearchResponse:
        from .models import RetrievalTrace

        if trace is None:
            trace = RetrievalTrace(
                query_normalized=request.query,
                retrieval_mode=RetrievalMode.UNAVAILABLE,
                corpus_id=manifest.corpus_id,
                manifest_refs=manifest_refs,
                risk_flags=risks,
                dense_available=False,
                sparse_available=False,
                graph_available=False,
            )
        else:
            trace = trace.model_copy(
                update={
                    "retrieval_mode": RetrievalMode.UNAVAILABLE,
                    "risk_flags": sorted(set([*trace.risk_flags, *risks])),
                }
            )
        return RetrievalSearchResponse(
            project_id=request.project_id,
            corpus_id=manifest.corpus_id,
            requested_mode=request.mode,
            retrieval_status="UNAVAILABLE",
            degraded_mode=RetrievalMode.UNAVAILABLE,
            candidate_papers=[],
            chunk_hits=[],
            retrieval_trace=trace,
            risk_flags=sorted(set(risks)),
            manifest_refs=manifest_refs,
        )

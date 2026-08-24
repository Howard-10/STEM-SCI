"""Tests for the bounded, graph-guided shared-corpus retrieval implementation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stem_sci import api
from stem_sci.context.models import ContextBuildRequest, VerificationStatus
from stem_sci.context.service import ContextService
from stem_sci.knowledge.evaluation import evaluate_gold_set
from stem_sci.knowledge.graph_retriever import GraphRetriever
from stem_sci.knowledge.hybrid_retriever import HybridRetriever
from stem_sci.knowledge.identity import PaperIdentityResolver
from stem_sci.knowledge.manifest import CorpusRegistry
from stem_sci.knowledge.models import ContextMode, RetrievalMode, RetrievalSearchRequest
from stem_sci.knowledge.retrievers import LocalMetadataCorpus, SparseRetriever
from stem_sci.knowledge.service import HybridKnowledgeService


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_assets(tmp_path: Path, *, locator: bool = False) -> None:
    catalog_dir = tmp_path / "data" / "catalogs" / "physics_stem"
    graph_dir = tmp_path / "data" / "derived" / "physics_stem"
    vector_dir = tmp_path / "data" / "local" / "vector_kb" / "vectordb"
    pdf_dir = tmp_path / "data" / "local" / "literature_pdfs"
    catalog_dir.mkdir(parents=True)
    graph_dir.mkdir(parents=True)
    vector_dir.mkdir(parents=True)
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "p1.pdf").write_bytes(b"placeholder PDF asset")
    (pdf_dir / "p2.pdf").write_bytes(b"placeholder PDF asset")
    catalog = {
        "artifact_type": "PaperIdentityMap",
        "paper_count": 2,
        "papers": [
            {
                "paper_id": "paper-ai",
                "title": "Generative AI scaffolding in physics education",
                "source_filename": "p1.pdf",
                "vector_filename": "p1.pdf",
                "doi": "10.1000/AI.1",
                "journal": "Demo Journal",
                "year": 2026,
            },
            {
                "paper_id": "paper-pbl",
                "title": "Project based learning in thermodynamics",
                "source_filename": "p2.pdf",
                "vector_filename": "p2.pdf",
                "doi": None,
                "journal": "Demo Journal",
                "year": 2025,
            },
        ],
    }
    graph = {
        "artifact_type": "SparsePaperGraph",
        "paper_count": 2,
        "total_triples": 4,
        "source_status": "model_generated_unverified",
        "papers": [
            {
                "paper_id": "paper-ai",
                "title": "Generative AI scaffolding in physics education",
                "triples": [
                    {"relation": "ADOPTS_PEDAGOGY", "tail": "Instructional Scaffolding"},
                    {"relation": "STUDIES_DOMAIN", "tail": "Physics Education"},
                ],
            },
            {
                "paper_id": "paper-pbl",
                "title": "Project based learning in thermodynamics",
                "triples": [
                    {"relation": "ADOPTS_PEDAGOGY", "tail": "Project Based Learning"},
                    {"relation": "STUDIES_DOMAIN", "tail": "Thermodynamics"},
                ],
            },
        ],
    }
    metadata = [
        {
            "filename": "p1.pdf",
            "doi": "https://doi.org/10.1000/ai.1",
            "paper_title": "Generative AI scaffolding in physics education",
            "section_hint": "Abstract",
            "chunk_index": 0,
            "text": "Generative AI instructional scaffolding improves physics modelling practice.",
        },
        {
            "filename": "p1.pdf",
            "doi": "10.1000/ai.1",
            "paper_title": "Generative AI scaffolding in physics education",
            "section_hint": "Results",
            "chunk_index": 1,
            "text": "Pre-service teachers reported support for transfer and modelling.",
        },
        {
            "filename": "p2.pdf",
            "doi": None,
            "paper_title": "Project based learning in thermodynamics",
            "section_hint": "Abstract",
            "chunk_index": 0,
            "text": "Project based learning supports thermodynamics conceptual understanding.",
        },
    ]
    catalog_path = catalog_dir / "paper_identity_map.json"
    graph_path = graph_dir / "sparse_paper_graph_v2.json"
    metadata_path = vector_dir / "metadata.json"
    index_path = vector_dir / "index.faiss"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    index_path.write_bytes(b"test index without faiss")
    locator_path = catalog_dir / "locator.json"
    if locator:
        resolver = PaperIdentityResolver.from_catalog_path(catalog_path)
        corpus = LocalMetadataCorpus.from_metadata_path(metadata_path, resolver)
        locator_records = []
        for record in corpus.records:
            pdf_path = pdf_dir / record.vector_filename
            locator_records.append(
                {
                    "canonical_chunk_id": record.canonical_chunk_id,
                    "canonical_paper_id": record.canonical_paper_id,
                    "source_filename": record.source_filename,
                    "pdf_relative_path": record.vector_filename,
                    "pdf_sha256": _sha256(pdf_path),
                    "chunk_index": record.chunk_index,
                    "quote_sha256": hashlib.sha256(record.text.encode("utf-8")).hexdigest(),
                    "page_start": 1,
                    "page_end": 1,
                    "char_start": 0,
                    "char_end": len(record.text),
                    "source_locator_method": "PAGE_TEXT_EXACT",
                    "verification_status": "source_verified",
                    "verification_note": "Synthetic verified locator",
                }
            )
        locator_path.write_text(
            json.dumps(
                {
                    "artifact_type": "PhysicsStemChunkLocatorIndex",
                    "artifact_version": "test-v1",
                    "corpus_id": "physics_stem_v1",
                    "corpus_version": "test-v1",
                    "generated_at": "2026-08-24T00:00:00Z",
                    "paper_count": 2,
                    "chunk_count": 3,
                    "resolved_count": 3,
                    "source_verified_count": 3,
                    "unresolved_count": 0,
                    "records": locator_records,
                }
            ),
            encoding="utf-8",
        )
    manifest = {
        "corpus_id": "physics_stem_v1",
        "corpus_version": "test-v1",
        "access_mode": "internal_read_only",
        "paper_count": 2,
        "vector_chunk_count": 3,
        "embedding_model": "test-embedding",
        "embedding_dimension": 2,
        "sparse_index_type": "BM25",
        "sparse_index_version": "test-v1",
        "graph_artifact_type": "SparsePaperGraph",
        "graph_paper_count": 2,
        "graph_triple_count": 4,
        "graph_prompt_version": "test",
        "identity_map": {
            "relative_path": "data/catalogs/physics_stem/paper_identity_map.json",
            "sha256": _sha256(catalog_path),
            "required": True,
        },
        "graph_artifact": {
            "relative_path": "data/derived/physics_stem/sparse_paper_graph_v2.json",
            "sha256": _sha256(graph_path),
            "required": False,
        },
        "vector_metadata": {
            "relative_path": "data/local/vector_kb/vectordb/metadata.json",
            "sha256": _sha256(metadata_path),
            "required": True,
        },
        "vector_index": {
            "relative_path": "data/local/vector_kb/vectordb/index.faiss",
            "sha256": _sha256(index_path),
            "required": False,
        },
        "pdf_root_relative_path": "data/local/literature_pdfs",
        "locator_index": (
            {
                "relative_path": "data/catalogs/physics_stem/locator.json",
                "sha256": _sha256(locator_path),
                "required": True,
            }
            if locator
            else None
        ),
        "published_at": "2026-08-12T00:00:00Z",
    }
    (catalog_dir / "physics_stem_v1.manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )


@pytest.fixture
def registry(tmp_path: Path) -> CorpusRegistry:
    _write_assets(tmp_path)
    return CorpusRegistry(tmp_path)


def test_identity_uses_stable_paper_key_not_source_file_sha(registry: CorpusRegistry) -> None:
    resolver = PaperIdentityResolver.from_catalog_path(
        registry.asset_path(registry.load_manifest().identity_map)
    )
    by_filename = resolver.resolve(filename="p1.pdf")
    by_doi = resolver.resolve(doi="https://doi.org/10.1000/AI.1")
    assert by_filename is not None
    assert by_doi is not None
    assert by_filename.canonical_paper_id == by_doi.canonical_paper_id
    assert not by_filename.canonical_paper_id.endswith("10.1000/ai.1")
    assert resolver.resolve(title="Generative AI scaffolding in physics education", year=2025) is None


def test_readiness_allows_discovery_but_blocks_formal_without_locator(registry: CorpusRegistry) -> None:
    readiness = registry.readiness()
    assert readiness.discovery_ready is True
    assert readiness.formal_evidence_ready is False
    assert "formal_locator_index_unavailable" in readiness.risk_flags


def test_graph_navigation_is_bounded_and_unverified(registry: CorpusRegistry) -> None:
    manifest = registry.load_manifest()
    resolver = PaperIdentityResolver.from_catalog_path(registry.asset_path(manifest.identity_map))
    graph = GraphRetriever(registry.asset_path(manifest.graph_artifact), resolver)
    candidates = graph.search("生成式AI 支架 物理 建模", limit=20)
    assert len(candidates) == 1
    assert candidates[0].graph_paper_id == "paper-ai"
    assert candidates[0].source_status == "model_generated_unverified"
    assert all(reference.startswith("graph:") for reference in candidates[0].supporting_edge_refs)


def test_compact_chinese_query_keeps_bounded_domain_concepts(registry: CorpusRegistry) -> None:
    manifest = registry.load_manifest()
    resolver = PaperIdentityResolver.from_catalog_path(registry.asset_path(manifest.identity_map))
    graph = GraphRetriever(registry.asset_path(manifest.graph_artifact), resolver)
    candidates = graph.search("生成式AI支架物理建模师范生", limit=5)
    assert candidates
    assert candidates[0].graph_paper_id == "paper-ai"


def test_sparse_retriever_rebuilds_bm25_and_returns_stable_ranks(registry: CorpusRegistry) -> None:
    manifest = registry.load_manifest()
    resolver = PaperIdentityResolver.from_catalog_path(registry.asset_path(manifest.identity_map))
    corpus = LocalMetadataCorpus.from_metadata_path(registry.asset_path(manifest.vector_metadata), resolver)
    hits = SparseRetriever(corpus).search("physics modelling scaffolding", limit=3)
    assert hits[0].source_filename == "p1.pdf"
    assert [hit.sparse_rank for hit in hits] == list(range(1, len(hits) + 1))


def test_graph_score_never_changes_rrf_score(registry: CorpusRegistry) -> None:
    manifest = registry.load_manifest()
    resolver = PaperIdentityResolver.from_catalog_path(registry.asset_path(manifest.identity_map))
    corpus = LocalMetadataCorpus.from_metadata_path(registry.asset_path(manifest.vector_metadata), resolver)
    sparse = SparseRetriever(corpus)
    graph = GraphRetriever(registry.asset_path(manifest.graph_artifact), resolver)
    retriever = HybridRetriever(
        corpus_id=manifest.corpus_id,
        manifest_refs=["manifest:test"],
        graph_retriever=graph,
        dense_search=None,
        sparse_search=sparse.search,
    )
    hits, trace = retriever.retrieve("generative AI scaffolding physics", limit=3)
    assert trace.retrieval_mode is RetrievalMode.SPARSE_ONLY
    assert all(hit.rrf_score == pytest.approx(1 / (60 + (hit.sparse_rank or 0))) for hit in hits)


def test_graph_failure_degrades_to_sparse_without_fake_hybrid(registry: CorpusRegistry) -> None:
    manifest = registry.load_manifest()
    resolver = PaperIdentityResolver.from_catalog_path(registry.asset_path(manifest.identity_map))
    corpus = LocalMetadataCorpus.from_metadata_path(registry.asset_path(manifest.vector_metadata), resolver)
    sparse = SparseRetriever(corpus)
    retriever = HybridRetriever(
        corpus_id=manifest.corpus_id,
        manifest_refs=["manifest:test"],
        graph_retriever=None,
        dense_search=None,
        sparse_search=sparse.search,
    )
    hits, trace = retriever.retrieve("physics", limit=3)
    assert hits
    assert trace.retrieval_mode is RetrievalMode.SPARSE_ONLY
    assert "graph_navigation_unavailable" in trace.risk_flags


def test_discovery_context_is_traceable_but_formal_context_fails_closed(
    tmp_path: Path, registry: CorpusRegistry
) -> None:
    service = HybridKnowledgeService(ContextService(tmp_path / "state"), registry)
    discovery = service.build_context(
        project_id="alpha",
        task_ref="scope",
        query="generative AI scaffolding physics",
        token_budget=500,
        mode="discovery",
    )
    assert discovery.context_mode == "discovery"
    assert discovery.evidence_refs
    assert discovery.evidence_refs[0].verification_status is VerificationStatus.MODEL_GENERATED_UNVERIFIED
    assert discovery.retrieval_strategy == "hybrid"
    assert discovery.manifest_refs
    formal = service.build_context(
        project_id="alpha",
        task_ref="protocol",
        query="generative AI scaffolding physics",
        token_budget=500,
        mode="formal",
    )
    assert formal.context_mode == "formal"
    assert formal.evidence_refs == []
    assert "insufficient_verified_evidence" in formal.risk_flags
    assert "formal_locator_index_unavailable" in formal.retrieval_risk_flags


def test_development_mode_allows_unverified_formal_context(
    tmp_path: Path, registry: CorpusRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STEM_SCI_ALLOW_UNVERIFIED_FORMAL_EVIDENCE", "true")
    service = HybridKnowledgeService(ContextService(tmp_path / "state"), registry)

    formal = service.build_context(
        project_id="alpha",
        task_ref="protocol-development",
        query="generative AI scaffolding physics",
        token_budget=500,
        mode="formal",
    )

    assert formal.context_mode == "formal"
    assert formal.evidence_refs
    assert all(
        item.verification_status is VerificationStatus.MODEL_GENERATED_UNVERIFIED
        for item in formal.evidence_refs
    )
    assert "UNVERIFIED_FORMAL_EVIDENCE_ENABLED" in formal.risk_flags


def test_graph_navigation_is_only_reported_for_graph_nominated_papers(
    tmp_path: Path, registry: CorpusRegistry
) -> None:
    service = HybridKnowledgeService(ContextService(tmp_path / "state"), registry)
    response = service.search(
        RetrievalSearchRequest(
            project_id="alpha",
            query="generative AI scaffolding physics",
            mode=ContextMode.DISCOVERY,
        )
    )
    nominated = {candidate.canonical_paper_id for candidate in response.candidate_papers}
    assert nominated
    assert response.chunk_hits
    for hit in response.chunk_hits:
        assert ("graph_navigation" in hit.retrieval_modalities) is (
            hit.canonical_paper_id in nominated
        )


def test_manifest_hash_change_blocks_discovery(tmp_path: Path) -> None:
    _write_assets(tmp_path)
    metadata = tmp_path / "data" / "local" / "vector_kb" / "vectordb" / "metadata.json"
    metadata.write_text("[]", encoding="utf-8")
    registry = CorpusRegistry(tmp_path)
    response = HybridKnowledgeService(ContextService(tmp_path / "state"), registry).search(
        RetrievalSearchRequest(project_id="alpha", query="physics", mode=ContextMode.DISCOVERY)
    )
    assert response.retrieval_status == "UNAVAILABLE"
    assert any(flag.startswith("asset_hash_mismatch") for flag in response.risk_flags)


def test_manifest_content_count_mismatch_blocks_discovery(tmp_path: Path) -> None:
    _write_assets(tmp_path)
    metadata = tmp_path / "data" / "local" / "vector_kb" / "vectordb" / "metadata.json"
    manifest_path = tmp_path / "data" / "catalogs" / "physics_stem" / "physics_stem_v1.manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["vector_chunk_count"] = 4
    payload["vector_metadata"]["sha256"] = _sha256(metadata)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    registry = CorpusRegistry(tmp_path)
    response = HybridKnowledgeService(ContextService(tmp_path / "state"), registry).search(
        RetrievalSearchRequest(project_id="alpha", query="physics", mode=ContextMode.DISCOVERY)
    )
    assert response.retrieval_status == "UNAVAILABLE"
    assert any(flag.startswith("asset_content_mismatch") for flag in response.risk_flags)


def test_hybrid_api_does_not_expose_absolute_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_assets(tmp_path)
    local_service = ContextService(tmp_path / "state")
    local_knowledge_service = HybridKnowledgeService(local_service, CorpusRegistry(tmp_path))
    monkeypatch.setattr(api, "knowledge_service", local_knowledge_service)
    client = TestClient(api.app)
    response = client.post(
        "/api/v1/retrieval/search",
        json={"project_id": "alpha", "query": "physics scaffolding", "mode": "discovery"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["retrieval_status"] == "DEGRADED"
    assert payload["retrieval_trace"]["retrieval_mode"] == "SPARSE_ONLY"
    assert "C:\\" not in response.text
    assert str(tmp_path) not in response.text


def test_existing_local_context_model_remains_backwards_compatible(tmp_path: Path) -> None:
    service = ContextService(tmp_path)
    source = service.import_bytes("alpha", "source.md", b"Physics evidence")
    bundle = service.build(
        ContextBuildRequest(
            project_id="alpha",
            task_ref="legacy",
            query="Physics",
            token_budget=100,
            allowed_verification_statuses=[VerificationStatus.MODEL_GENERATED_UNVERIFIED],
        )
    )
    assert source.source_id in bundle.source_refs
    assert bundle.context_mode == "local"
    assert bundle.retrieval_strategy == "local_keyword"


def test_evaluation_refuses_a_non_frozen_gold_set() -> None:
    with pytest.raises(ValueError, match="FROZEN"):
        evaluate_gold_set(
            json.dumps({"corpus_id": "physics_stem_v1", "status": "ANNOTATION_REQUIRED", "questions": []}),
            lambda request: pytest.fail(f"must not search {request.query}"),
        )


def test_evaluation_calculates_metrics_only_from_verified_labels() -> None:
    from stem_sci.knowledge.models import (
        RetrievalHitSummary,
        RetrievalSearchResponse,
        RetrievalTrace,
    )

    def fake_search(request: RetrievalSearchRequest) -> RetrievalSearchResponse:
        hit = RetrievalHitSummary(
            canonical_chunk_id="chunk-1",
            canonical_paper_id="paper-1",
            source_filename="p1.pdf",
            paper_title="Paper",
            chunk_index=0,
            excerpt="Evidence",
            locator_status="RESOLVED",
        )
        trace = RetrievalTrace(
            query_normalized=request.query,
            retrieval_mode=RetrievalMode.SPARSE_ONLY,
            corpus_id="physics_stem_v1",
            manifest_refs=[],
            dense_available=False,
            sparse_available=True,
            graph_available=False,
        )
        return RetrievalSearchResponse(
            project_id=request.project_id,
            corpus_id="physics_stem_v1",
            requested_mode=ContextMode.DISCOVERY,
            retrieval_status="DEGRADED",
            degraded_mode=RetrievalMode.SPARSE_ONLY,
            candidate_papers=[],
            chunk_hits=[hit],
            retrieval_trace=trace,
            risk_flags=[],
            manifest_refs=[],
        )

    report = evaluate_gold_set(
        json.dumps(
            {
                "corpus_id": "physics_stem_v1",
                "status": "FROZEN",
                "questions": [
                    {
                        "question_id": "q1",
                        "language": "en",
                        "query": "query",
                        "relevant_paper_ids": ["paper-1"],
                        "strongly_relevant_chunk_ids": ["chunk-1"],
                        "annotation_status": "VERIFIED",
                    }
                ],
            }
        ),
        fake_search,
    )
    assert report.paper_recall_at_5 == 1.0
    assert report.chunk_hit_rate_at_5 == 1.0
    assert report.mean_reciprocal_rank == 1.0


def test_valid_locator_allows_source_verified_formal_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_assets(tmp_path, locator=True)
    monkeypatch.setattr(
        "stem_sci.knowledge.service.DenseRetriever.search",
        lambda self, query, limit: [],
    )
    service = HybridKnowledgeService(ContextService(tmp_path / "state"), CorpusRegistry(tmp_path))

    readiness = service.readiness("physics_stem_v1")
    assert readiness.formal_evidence_ready is True
    response = service.search(
        RetrievalSearchRequest(
            project_id="alpha",
            query="generative AI physics",
            mode=ContextMode.FORMAL,
        )
    )
    assert response.chunk_hits
    assert all(hit.locator_status == "RESOLVED" for hit in response.chunk_hits)
    assert all(hit.verification_status == "source_verified" for hit in response.chunk_hits)
    assert all(hit.page_start == 1 for hit in response.chunk_hits)

    bundle = service.build_context(
        project_id="alpha",
        task_ref="formal-evidence",
        query="generative AI physics",
        token_budget=500,
        mode="formal",
    )
    assert bundle.evidence_refs
    assert all(
        item.verification_status is VerificationStatus.SOURCE_VERIFIED
        for item in bundle.evidence_refs
    )
    assert all(item.location.page_start == 1 for item in bundle.evidence_refs)


def test_pdf_tamper_blocks_formal_but_keeps_discovery_ready(tmp_path: Path) -> None:
    _write_assets(tmp_path, locator=True)
    (tmp_path / "data/local/literature_pdfs/p1.pdf").write_bytes(b"tampered PDF asset")
    registry = CorpusRegistry(tmp_path)

    readiness = registry.readiness()
    assert readiness.discovery_ready is True
    assert readiness.formal_evidence_ready is False
    assert "formal_locator_index_invalid" in readiness.risk_flags

    response = HybridKnowledgeService(ContextService(tmp_path / "state"), registry).search(
        RetrievalSearchRequest(project_id="alpha", query="physics", mode=ContextMode.FORMAL)
    )
    assert response.retrieval_status == "UNAVAILABLE"
    assert response.chunk_hits == []
"""Typed contracts for corpus assets and graph-guided retrieval."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictKnowledgeModel(BaseModel):
    """Reject ambiguous data at a retrieval boundary."""

    model_config = ConfigDict(extra="forbid")


class ContextMode(StrEnum):
    """Permitted use of an assembled retrieval bundle."""

    DISCOVERY = "discovery"
    FORMAL = "formal"


class RetrievalStrategy(StrEnum):
    """Supported ContextBundle retrieval paths."""

    LOCAL_KEYWORD = "local_keyword"
    HYBRID = "hybrid"


class RetrievalMode(StrEnum):
    """Actual retrieval mode, including explicit degradation."""

    HYBRID_GRAPH_GUIDED = "HYBRID_GRAPH_GUIDED"
    HYBRID_DENSE_SPARSE = "HYBRID_DENSE_SPARSE"
    SPARSE_ONLY = "SPARSE_ONLY"
    DENSE_ONLY = "DENSE_ONLY"
    UNAVAILABLE = "UNAVAILABLE"


class CorpusAccessMode(StrEnum):
    """Runtime mutability of a corpus."""

    INTERNAL_READ_ONLY = "internal_read_only"
    PROJECT_PRIVATE = "project_private"


class AssetRef(StrictKnowledgeModel):
    """A relative, hash-addressed asset reference without a local absolute path."""

    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    required: bool = True


class CorpusManifest(StrictKnowledgeModel):
    """Versioned declaration of all assets needed by a shared corpus."""

    corpus_id: str = Field(min_length=1)
    corpus_version: str = Field(min_length=1)
    access_mode: CorpusAccessMode
    paper_count: int = Field(ge=0)
    vector_chunk_count: int = Field(ge=0)
    embedding_model: str = Field(min_length=1)
    embedding_dimension: int = Field(gt=0)
    sparse_index_type: str = Field(min_length=1)
    sparse_index_version: str = Field(min_length=1)
    graph_artifact_type: str = Field(min_length=1)
    graph_paper_count: int = Field(ge=0)
    graph_triple_count: int = Field(ge=0)
    graph_prompt_version: str = Field(min_length=1)
    identity_map: AssetRef
    graph_artifact: AssetRef
    vector_metadata: AssetRef
    vector_index: AssetRef
    pdf_root_relative_path: str = Field(min_length=1)
    locator_index: AssetRef | None = None
    published_at: str = Field(min_length=1)


class AssetCheck(StrictKnowledgeModel):
    """One non-sensitive result from asset validation."""

    relative_path: str
    state: Literal["READY", "MISSING", "HASH_MISMATCH", "CONTENT_MISMATCH"]
    required: bool


class CorpusReadiness(StrictKnowledgeModel):
    """Readiness result used by APIs and the hybrid provider."""

    corpus_id: str
    corpus_version: str
    discovery_ready: bool
    formal_evidence_ready: bool
    checks: list[AssetCheck]
    risk_flags: list[str] = Field(default_factory=list)


class SharedCorpusSummary(StrictKnowledgeModel):
    """Public, safe status summary for one read-only shared corpus."""

    corpus_id: str
    corpus_version: str
    access_mode: CorpusAccessMode
    paper_count: int = Field(ge=0)
    vector_chunk_count: int = Field(ge=0)
    discovery_ready: bool
    formal_evidence_ready: bool
    risk_flags: list[str] = Field(default_factory=list)


class CanonicalPaper(StrictKnowledgeModel):
    """Stable paper identity; separate from a particular PDF SHA256."""

    canonical_paper_id: str
    graph_paper_id: str
    title: str
    normalized_doi: str | None = None
    year: int | None = None
    journal: str | None = None
    source_filename: str
    vector_filename: str
    identity_status: Literal["RESOLVED", "POSSIBLE_DUPLICATE", "UNRESOLVED"] = "RESOLVED"


class GraphCandidate(StrictKnowledgeModel):
    """A paper candidate from unverified, navigation-only graph edges."""

    canonical_paper_id: str
    graph_paper_id: str
    navigation_score: float = Field(ge=0)
    matched_facets: list[str]
    supporting_edge_refs: list[str]
    source_status: Literal["model_generated_unverified"] = "model_generated_unverified"


class RetrievalHit(StrictKnowledgeModel):
    """One raw-text chunk hit; text is internal and never required in API output."""

    canonical_chunk_id: str
    canonical_paper_id: str
    source_filename: str
    paper_title: str
    normalized_doi: str | None = None
    chunk_index: int = Field(ge=0)
    section_hint: str | None = None
    text: str
    dense_rank: int | None = Field(default=None, ge=1)
    sparse_rank: int | None = Field(default=None, ge=1)
    rrf_score: float = Field(default=0, ge=0)


class RetrievalTrace(StrictKnowledgeModel):
    """A reproducible, non-secret trace of a retrieval attempt."""

    query_normalized: str
    retrieval_mode: RetrievalMode
    corpus_id: str
    manifest_refs: list[str]
    graph_candidates: list[GraphCandidate] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    dense_available: bool
    sparse_available: bool
    graph_available: bool


class RetrievalSearchRequest(StrictKnowledgeModel):
    """API request for a shared-corpus retrieval operation."""

    project_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    corpus_ids: list[str] = Field(default_factory=lambda: ["physics_stem_v1"], min_length=1)
    query: str = Field(min_length=1, max_length=20_000)
    mode: ContextMode = ContextMode.DISCOVERY
    limit: int = Field(default=8, ge=1, le=20)


class HybridContextBuildRequest(StrictKnowledgeModel):
    """Explicit build request for the read-only shared hybrid corpus."""

    project_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    task_ref: str = Field(min_length=1)
    query: str = Field(min_length=1, max_length=20_000)
    token_budget: int = Field(gt=0, le=20_000)
    mode: ContextMode = ContextMode.DISCOVERY


class RetrievalHitSummary(StrictKnowledgeModel):
    """Public, bounded representation of a raw-text hit."""

    canonical_chunk_id: str
    canonical_paper_id: str
    source_filename: str
    paper_title: str
    normalized_doi: str | None = None
    chunk_index: int
    section_hint: str | None = None
    excerpt: str
    dense_rank: int | None = None
    sparse_rank: int | None = None
    rrf_score: float = 0
    locator_status: Literal["RESOLVED", "UNRESOLVED"]
    retrieval_modalities: list[Literal["dense", "sparse", "graph_navigation"]] = Field(
        default_factory=list
    )


class RetrievalSearchResponse(StrictKnowledgeModel):
    """Public result from graph-guided hybrid retrieval."""

    project_id: str
    corpus_id: str
    requested_mode: ContextMode
    retrieval_status: Literal["READY", "DEGRADED", "UNAVAILABLE"]
    degraded_mode: RetrievalMode | None = None
    candidate_papers: list[GraphCandidate]
    chunk_hits: list[RetrievalHitSummary]
    retrieval_trace: RetrievalTrace
    risk_flags: list[str]
    manifest_refs: list[str]

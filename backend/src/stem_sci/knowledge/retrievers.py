"""Local sparse and optional dense retrievers over a shared chunk corpus."""

from __future__ import annotations

import json
import math
import os
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Protocol, cast

from pydantic import BaseModel, ConfigDict, Field

from .identity import PaperIdentityResolver
from .models import RetrievalHit
from .normalization import expanded_query, normalize_doi, tokenize


class RetrievalUnavailable(RuntimeError):
    """A declared retriever cannot run in this environment."""


class _MetadataRecord(BaseModel):
    """Projection of one local vector metadata record."""

    model_config = ConfigDict(extra="ignore")

    filename: str = Field(min_length=1)
    doi: str | None = None
    paper_title: str = ""
    section_hint: str | None = None
    chunk_index: int = Field(ge=0)
    text: str = Field(min_length=1)


@dataclass(frozen=True)
class ChunkRecord:
    """Internal raw-text chunk record with a resolved paper identity."""

    canonical_chunk_id: str
    canonical_paper_id: str
    source_filename: str
    vector_filename: str
    paper_title: str
    normalized_doi: str | None
    chunk_index: int
    section_hint: str | None
    text: str

    def to_hit(self) -> RetrievalHit:
        return RetrievalHit(
            canonical_chunk_id=self.canonical_chunk_id,
            canonical_paper_id=self.canonical_paper_id,
            source_filename=self.source_filename,
            paper_title=self.paper_title,
            normalized_doi=self.normalized_doi,
            chunk_index=self.chunk_index,
            section_hint=self.section_hint,
            text=self.text,
        )


class LocalMetadataCorpus:
    """Resolve vector metadata to canonical paper and chunk identities."""

    def __init__(self, records: list[ChunkRecord]) -> None:
        self.records = records

    @classmethod
    def from_metadata_path(
        cls,
        path: Path,
        resolver: PaperIdentityResolver,
    ) -> LocalMetadataCorpus:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("Vector metadata must be a JSON array")
        records: list[ChunkRecord] = []
        unresolved: list[int] = []
        for position, item in enumerate(raw):
            metadata = _MetadataRecord.model_validate(item)
            paper = resolver.resolve(
                filename=metadata.filename,
                doi=metadata.doi,
                title=metadata.paper_title or None,
            )
            if paper is None:
                unresolved.append(position)
                continue
            text_hash = sha256(metadata.text.encode("utf-8")).hexdigest()[:12]
            records.append(
                ChunkRecord(
                    canonical_chunk_id=(
                        f"chk_{paper.canonical_paper_id}_{metadata.chunk_index}_{text_hash}"
                    ),
                    canonical_paper_id=paper.canonical_paper_id,
                    source_filename=paper.source_filename,
                    vector_filename=metadata.filename,
                    paper_title=paper.title,
                    normalized_doi=normalize_doi(metadata.doi) or paper.normalized_doi,
                    chunk_index=metadata.chunk_index,
                    section_hint=metadata.section_hint,
                    text=metadata.text,
                )
            )
        if unresolved:
            raise ValueError(f"Vector metadata contains {len(unresolved)} unresolved paper records")
        return cls(records)


class SparseRetriever:
    """A reproducible in-memory BM25 index built from local metadata text."""

    def __init__(self, corpus: LocalMetadataCorpus, *, k1: float = 1.2, b: float = 0.75) -> None:
        if not corpus.records:
            raise ValueError("SparseRetriever requires at least one chunk")
        self._records = corpus.records
        self._k1 = k1
        self._b = b
        self._term_frequencies = [Counter(tokenize(record.text)) for record in self._records]
        self._document_frequencies: Counter[str] = Counter()
        for frequencies in self._term_frequencies:
            self._document_frequencies.update(frequencies.keys())
        self._lengths = [sum(frequencies.values()) for frequencies in self._term_frequencies]
        self._average_length = sum(self._lengths) / len(self._lengths)

    def search(self, query: str, limit: int) -> list[RetrievalHit]:
        """Rank chunks by BM25 with stable tie-breaking."""

        query_terms = list(dict.fromkeys(tokenize(expanded_query(query))))
        if not query_terms:
            return []
        scores: list[tuple[float, int]] = []
        total_documents = len(self._records)
        for position, frequencies in enumerate(self._term_frequencies):
            score = 0.0
            for term in query_terms:
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                document_frequency = self._document_frequencies[term]
                inverse_frequency = math.log(
                    1 + (total_documents - document_frequency + 0.5) / (document_frequency + 0.5)
                )
                denominator = frequency + self._k1 * (
                    1 - self._b + self._b * self._lengths[position] / self._average_length
                )
                score += inverse_frequency * frequency * (self._k1 + 1) / denominator
            if score > 0:
                scores.append((score, position))
        ordered = sorted(
            scores,
            key=lambda item: (
                -item[0],
                self._records[item[1]].canonical_paper_id,
                self._records[item[1]].chunk_index,
                self._records[item[1]].canonical_chunk_id,
            ),
        )[:limit]
        hits: list[RetrievalHit] = []
        for rank, (_, position) in enumerate(ordered, start=1):
            hits.append(self._records[position].to_hit().model_copy(update={"sparse_rank": rank}))
        return hits


class QueryEmbedder(Protocol):
    """Minimal pluggable query-embedding boundary."""

    def __call__(self, query: str) -> Sequence[float]: ...


class DashScopeQueryEmbedder:
    """Optional runtime adapter; it sends only the user query to DashScope."""

    def __call__(self, query: str) -> Sequence[float]:
        api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
        if not api_key:
            raise RetrievalUnavailable("DASHSCOPE_API_KEY is not configured")
        try:
            import dashscope  # type: ignore[import-not-found, unused-ignore]
        except ImportError as error:
            raise RetrievalUnavailable("dashscope dependency is not installed") from error
        dashscope.api_key = api_key
        response = dashscope.TextEmbedding.call(model="text-embedding-v3", input=[query])
        if response.status_code != 200:
            raise RetrievalUnavailable("DashScope query embedding failed")
        return cast(Sequence[float], response.output["embeddings"][0]["embedding"])


class DenseRetriever:
    """Optional FAISS retrieval; unavailable dependencies cause explicit degradation."""

    def __init__(
        self,
        corpus: LocalMetadataCorpus,
        index_path: Path,
        embedder: QueryEmbedder | None = None,
    ) -> None:
        self._corpus = corpus
        self._index_path = index_path
        self._embedder = embedder or DashScopeQueryEmbedder()

    def search(self, query: str, limit: int) -> list[RetrievalHit]:
        """Search the declared FAISS index with the same 1024-dimensional query model."""

        try:
            import faiss  # type: ignore[import-not-found, unused-ignore]
            import numpy as np
        except ImportError as error:
            raise RetrievalUnavailable("faiss-cpu retrieval dependencies are not installed") from error
        if not self._index_path.is_file():
            raise RetrievalUnavailable("FAISS index is unavailable")
        try:
            # Read bytes in Python first. On Windows, FAISS's native
            # read_index(path) may fail when the absolute path contains
            # non-ASCII characters, even though the file exists.
            index_bytes = self._index_path.read_bytes()
            index = faiss.deserialize_index(
                np.frombuffer(index_bytes, dtype="uint8")
            )
        except (OSError, RuntimeError, ValueError) as error:
            raise RetrievalUnavailable("FAISS index could not be opened") from error
        if index.ntotal != len(self._corpus.records):
            raise RetrievalUnavailable("FAISS index and vector metadata counts differ")
        vector = np.asarray(self._embedder(query), dtype="float32").reshape(1, -1)
        if vector.shape[1] != index.d:
            raise RetrievalUnavailable("Query embedding dimension does not match FAISS index")
        faiss.normalize_L2(vector)
        _, positions = index.search(vector, limit)
        hits: list[RetrievalHit] = []
        for rank, position in enumerate(positions[0], start=1):
            if position < 0:
                continue
            hits.append(self._corpus.records[int(position)].to_hit().model_copy(update={"dense_rank": rank}))
        return hits

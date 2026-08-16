"""Two-stage graph-guided hybrid ranking with explicit degraded modes."""

from __future__ import annotations

from collections.abc import Callable

from .graph_retriever import GraphRetriever
from .models import GraphCandidate, RetrievalHit, RetrievalMode, RetrievalTrace
from .normalization import expanded_query
from .retrievers import RetrievalUnavailable


class HybridRetriever:
    """Use graph navigation for candidates and RRF only for text retriever ranks."""

    def __init__(
        self,
        *,
        corpus_id: str,
        manifest_refs: list[str],
        graph_retriever: GraphRetriever | None,
        dense_search: Callable[[str, int], list[RetrievalHit]] | None,
        sparse_search: Callable[[str, int], list[RetrievalHit]] | None,
    ) -> None:
        self._corpus_id = corpus_id
        self._manifest_refs = manifest_refs
        self._graph_retriever = graph_retriever
        self._dense_search = dense_search
        self._sparse_search = sparse_search

    def retrieve(self, query: str, limit: int = 8) -> tuple[list[RetrievalHit], RetrievalTrace]:
        """Retrieve chunks using transparent two-stage candidate selection and RRF."""

        risks: list[str] = []
        graph_candidates: list[GraphCandidate] = []
        graph_available = self._graph_retriever is not None
        if self._graph_retriever is not None:
            try:
                graph_candidates = self._graph_retriever.search(query, limit=20)
            except (OSError, ValueError) as error:
                graph_available = False
                risks.append(f"graph_navigation_unavailable:{type(error).__name__}")
        else:
            risks.append("graph_navigation_unavailable")

        dense_hits, dense_available = self._search(self._dense_search, query, "dense", risks)
        sparse_hits, sparse_available = self._search(self._sparse_search, query, "sparse", risks)
        mode = self._mode(dense_available, sparse_available, graph_available, graph_candidates)
        trace = RetrievalTrace(
            query_normalized=expanded_query(query),
            retrieval_mode=mode,
            corpus_id=self._corpus_id,
            manifest_refs=self._manifest_refs,
            graph_candidates=graph_candidates,
            risk_flags=risks,
            dense_available=dense_available,
            sparse_available=sparse_available,
            graph_available=graph_available,
        )
        if mode is RetrievalMode.UNAVAILABLE:
            return [], trace
        return self._fuse(dense_hits, sparse_hits, graph_candidates, limit), trace

    @staticmethod
    def _search(
        search: Callable[[str, int], list[RetrievalHit]] | None,
        query: str,
        label: str,
        risks: list[str],
    ) -> tuple[list[RetrievalHit], bool]:
        if search is None:
            risks.append(f"{label}_retrieval_unavailable")
            return [], False
        try:
            return search(query, 80), True
        except RetrievalUnavailable as error:
            risks.append(f"{label}_retrieval_unavailable:{str(error)}")
            return [], False
        except (OSError, ValueError) as error:
            risks.append(f"{label}_retrieval_unavailable:{type(error).__name__}")
            return [], False

    @staticmethod
    def _mode(
        dense_available: bool,
        sparse_available: bool,
        graph_available: bool,
        graph_candidates: list[GraphCandidate],
    ) -> RetrievalMode:
        if dense_available and sparse_available:
            if graph_available and graph_candidates:
                return RetrievalMode.HYBRID_GRAPH_GUIDED
            return RetrievalMode.HYBRID_DENSE_SPARSE
        if sparse_available:
            return RetrievalMode.SPARSE_ONLY
        if dense_available:
            return RetrievalMode.DENSE_ONLY
        return RetrievalMode.UNAVAILABLE

    @staticmethod
    def _fuse(
        dense_hits: list[RetrievalHit],
        sparse_hits: list[RetrievalHit],
        graph_candidates: list[GraphCandidate],
        limit: int,
    ) -> list[RetrievalHit]:
        """Fuse only text ranks; graph scores merely choose a second candidate channel."""

        graph_paper_ids = {candidate.canonical_paper_id for candidate in graph_candidates}
        selected_ids: set[str] = set()
        selected_ids.update(hit.canonical_chunk_id for hit in dense_hits[:20])
        selected_ids.update(hit.canonical_chunk_id for hit in sparse_hits[:20])
        selected_ids.update(
            hit.canonical_chunk_id for hit in dense_hits if hit.canonical_paper_id in graph_paper_ids
        )
        selected_ids.update(
            hit.canonical_chunk_id for hit in sparse_hits if hit.canonical_paper_id in graph_paper_ids
        )

        dense_by_id = {hit.canonical_chunk_id: hit for hit in dense_hits}
        sparse_by_id = {hit.canonical_chunk_id: hit for hit in sparse_hits}
        fused: list[RetrievalHit] = []
        for chunk_id in selected_ids:
            dense = dense_by_id.get(chunk_id)
            sparse = sparse_by_id.get(chunk_id)
            base = dense or sparse
            if base is None:
                continue
            dense_rank = dense.dense_rank if dense is not None else None
            sparse_rank = sparse.sparse_rank if sparse is not None else None
            score = 0.0
            if dense_rank is not None:
                score += 1 / (60 + dense_rank)
            if sparse_rank is not None:
                score += 1 / (60 + sparse_rank)
            fused.append(
                base.model_copy(
                    update={
                        "dense_rank": dense_rank,
                        "sparse_rank": sparse_rank,
                        "rrf_score": score,
                    }
                )
            )
        paper_counts: dict[str, int] = {}
        result: list[RetrievalHit] = []
        for hit in sorted(
            fused,
            key=lambda item: (
                -item.rrf_score,
                item.canonical_paper_id,
                item.chunk_index,
                item.canonical_chunk_id,
            ),
        ):
            if paper_counts.get(hit.canonical_paper_id, 0) >= 2:
                continue
            paper_counts[hit.canonical_paper_id] = paper_counts.get(hit.canonical_paper_id, 0) + 1
            result.append(hit)
            if len(result) == limit:
                break
        return result

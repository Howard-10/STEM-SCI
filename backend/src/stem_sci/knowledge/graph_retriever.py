"""Deterministic one-hop navigation over the paper-level sparse graph."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .identity import PaperIdentityResolver
from .models import GraphCandidate
from .normalization import expanded_query, normalize_text, tokenize


class _GraphTriple(BaseModel):
    """Projection of a triple in the versioned graph artifact."""

    model_config = ConfigDict(extra="ignore")

    relation: str = Field(min_length=1)
    tail: str = Field(min_length=1)


class _GraphPaper(BaseModel):
    """Projection of graph content required for navigation."""

    model_config = ConfigDict(extra="ignore")

    paper_id: str = Field(min_length=1)
    title: str = ""
    triples: list[_GraphTriple] = Field(default_factory=list)


class _GraphArtifact(BaseModel):
    """Projection of the checked-in SparsePaperGraph artifact."""

    model_config = ConfigDict(extra="ignore")

    artifact_type: str
    paper_count: int = Field(ge=0)
    total_triples: int = Field(ge=0)
    source_status: str
    papers: list[_GraphPaper]


class GraphRetriever:
    """Use unverified triples only to nominate and explain paper candidates."""

    def __init__(self, graph_path: Path, resolver: PaperIdentityResolver) -> None:
        artifact = _GraphArtifact.model_validate_json(graph_path.read_text(encoding="utf-8"))
        if artifact.artifact_type != "SparsePaperGraph":
            raise ValueError("Graph artifact is not a SparsePaperGraph")
        if artifact.source_status != "model_generated_unverified":
            raise ValueError("Graph navigation artifact has an unexpected source status")
        if artifact.paper_count != len(artifact.papers):
            raise ValueError("Graph paper_count does not match records")
        self._papers = artifact.papers
        self._resolver = resolver

    def search(self, query: str, limit: int = 20) -> list[GraphCandidate]:
        """Return at most one candidate per resolved paper, ordered deterministically."""

        normalized_query = expanded_query(query)
        query_terms = set(tokenize(normalized_query))
        grouped_facets: dict[str, list[tuple[float, str, str]]] = defaultdict(list)
        for paper in self._papers:
            canonical = self._resolver.by_graph_paper_id(paper.paper_id)
            if canonical is None:
                continue
            title_score = self._match_score(normalized_query, query_terms, paper.title)
            if title_score:
                grouped_facets[canonical.canonical_paper_id].append(
                    (title_score, paper.title, f"graph:{paper.paper_id}:title")
                )
            for index, triple in enumerate(paper.triples):
                facet = f"{triple.tail} {triple.relation.replace('_', ' ')}"
                score = self._match_score(normalized_query, query_terms, facet)
                if score:
                    grouped_facets[canonical.canonical_paper_id].append(
                        (score, triple.tail, f"graph:{paper.paper_id}:{index}")
                    )
        candidates: list[GraphCandidate] = []
        for canonical_id, matches in grouped_facets.items():
            canonical = self._resolver.by_canonical_id(canonical_id)
            if canonical is None:
                continue
            ranked = sorted(matches, key=lambda item: (-item[0], item[1].casefold(), item[2]))
            facets = list(dict.fromkeys(match[1] for match in ranked))[:5]
            edge_refs = list(dict.fromkeys(match[2] for match in ranked))[:5]
            candidates.append(
                GraphCandidate(
                    canonical_paper_id=canonical.canonical_paper_id,
                    graph_paper_id=canonical.graph_paper_id,
                    navigation_score=round(sum(match[0] for match in ranked), 6),
                    matched_facets=facets,
                    supporting_edge_refs=edge_refs,
                )
            )
        return sorted(
            candidates,
            key=lambda candidate: (
                -candidate.navigation_score,
                candidate.graph_paper_id,
                candidate.canonical_paper_id,
            ),
        )[:limit]

    @staticmethod
    def _match_score(normalized_query: str, query_terms: set[str], facet: str) -> float:
        normalized_facet = normalize_text(facet)
        facet_terms = set(tokenize(facet))
        if not facet_terms:
            return 0.0
        phrase_score = 3.0 if len(normalized_facet) >= 4 and normalized_facet in normalized_query else 0.0
        overlap = len(query_terms.intersection(facet_terms))
        if overlap == 0:
            return phrase_score
        return phrase_score + overlap / len(facet_terms)

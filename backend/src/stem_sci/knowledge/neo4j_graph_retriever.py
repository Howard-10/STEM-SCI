"""Neo4j-backed paper navigation over the imported sparse graph."""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

from .identity import PaperIdentityResolver
from .models import GraphCandidate
from .normalization import expanded_query, normalize_text, tokenize


class Neo4jGraphRetriever:
    """Navigate papers through RELATES.paper_id without treating graph facts as evidence."""

    def __init__(
        self,
        resolver: PaperIdentityResolver,
        *,
        uri: str | None = None,
        username: str | None = None,
        password: str | None = None,
        database: str | None = None,
        project_id: str | None = None,
    ) -> None:
        try:
            from neo4j import GraphDatabase
        except ImportError as error:
            raise RuntimeError("neo4j dependency is not installed") from error

        self._resolver = resolver
        self._uri: str = uri or os.getenv("NEO4J_URI") or "bolt://localhost:7688"
        self._username: str = username or os.getenv("NEO4J_USERNAME") or "neo4j"
        self._password: str = password or os.getenv("NEO4J_PASSWORD") or ""
        self._database: str = database or os.getenv("NEO4J_DATABASE") or "neo4j"
        self._project_id: str = project_id or os.getenv("NEO4J_PROJECT_ID") or "stem-sci"
        if not self._password:
            raise ValueError("NEO4J_PASSWORD is required for Neo4j graph retrieval")
        self._driver = GraphDatabase.driver(
            self._uri,
            auth=(self._username, self._password),
        )
        self._driver.verify_connectivity()

    def close(self) -> None:
        self._driver.close()

    def search(self, query: str, limit: int = 20) -> list[GraphCandidate]:
        normalized_query = expanded_query(query)
        query_terms = set(tokenize(normalized_query))
        if not query_terms:
            return []
        rows = self._fetch_edges()
        grouped: dict[str, list[tuple[float, str, str]]] = defaultdict(list)
        for row in rows:
            paper_id = str(row.get("paper_id") or "").strip()
            if not paper_id:
                continue
            facet = " ".join(
                [
                    str(row.get("head") or ""),
                    str(row.get("relation") or "").replace("_", " "),
                    str(row.get("tail") or ""),
                    str(row.get("evidence") or ""),
                ]
            )
            score = self._match_score(normalized_query, query_terms, facet)
            if score:
                edge_ref = f"neo4j:{paper_id}:{row.get('relation')}:{row.get('tail')}"
                grouped[paper_id].append(
                    (score, str(row.get("tail") or row.get("head") or ""), edge_ref)
                )

        candidates: list[GraphCandidate] = []
        for graph_paper_id, matches in grouped.items():
            canonical = self._resolver.by_graph_paper_id(graph_paper_id)
            if canonical is None:
                continue
            ranked = sorted(matches, key=lambda item: (-item[0], item[1].casefold(), item[2]))
            candidates.append(
                GraphCandidate(
                    canonical_paper_id=canonical.canonical_paper_id,
                    graph_paper_id=canonical.graph_paper_id,
                    navigation_score=round(sum(item[0] for item in ranked), 6),
                    matched_facets=list(dict.fromkeys(item[1] for item in ranked))[:5],
                    supporting_edge_refs=list(dict.fromkeys(item[2] for item in ranked))[:5],
                )
            )
        return sorted(
            candidates,
            key=lambda item: (
                -item.navigation_score,
                item.graph_paper_id,
                item.canonical_paper_id,
            ),
        )[:limit]

    def _fetch_edges(self) -> list[dict[str, Any]]:
        query = """
        MATCH (h:Entity {project_id: $project_id})
              -[r:RELATES {project_id: $project_id}]->
              (t:Entity {project_id: $project_id})
        RETURN h.name AS head,
               h.entity_type AS head_type,
               r.relation_type AS relation,
               t.name AS tail,
               t.entity_type AS tail_type,
               r.evidence AS evidence,
               r.confidence AS confidence,
               r.paper_id AS paper_id
        ORDER BY coalesce(r.confidence, 0) DESC
        LIMIT $limit
        """
        with self._driver.session(database=self._database) as session:
            result = session.run(query, project_id=self._project_id, limit=5000)
            return [dict(record) for record in result]

    @staticmethod
    def _match_score(normalized_query: str, query_terms: set[str], facet: str) -> float:
        normalized_facet = normalize_text(facet)
        facet_terms = set(tokenize(facet))
        if not facet_terms:
            return 0.0
        phrase_score = (
            3.0
            if len(normalized_facet) >= 4 and normalized_facet in normalized_query
            else 0.0
        )
        overlap = len(query_terms.intersection(facet_terms))
        if overlap == 0:
            return phrase_score
        return phrase_score + overlap / len(facet_terms)

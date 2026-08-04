"""Minimal append-only lineage edge writer.

Cross-domain provenance graph construction belongs to ``stem_sci.provenance``.
"""

from __future__ import annotations

from pydantic import Field

from stem_sci.core.models import DomainModel


class LineageEdge(DomainModel):
    source_ref: str = Field(min_length=1)
    target_ref: str = Field(min_length=1)
    relation: str = Field(min_length=1)


class InMemoryLineageWriter:
    def __init__(self) -> None:
        self._edges: list[LineageEdge] = []

    def put(self, edge: LineageEdge) -> LineageEdge:
        if edge not in self._edges:
            self._edges.append(edge)
        return edge

    def list_edges(self, target_ref: str | None = None) -> list[LineageEdge]:
        if target_ref is None:
            return list(self._edges)
        return [edge for edge in self._edges if edge.target_ref == target_ref]

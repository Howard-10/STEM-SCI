"""Provider boundary for optional GraphRAG extraction.

The operator is deliberately smaller than a research Agent: it accepts an
approved extraction request, invokes a replaceable provider, and validates the
returned immutable candidate.  It never verifies evidence, writes a graph
database, or promotes triples into a formal ContextBundle.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .graph_schema import GraphExtractionRequest, GraphExtractionResult


class GraphExtractionUnavailable(RuntimeError):
    """Raised when no configured graph extraction provider is available."""


class GraphExtractionProvider(Protocol):
    """Minimal provider interface for a future deterministic/LLM adapter."""

    def extract(
        self,
        request: GraphExtractionRequest,
        source_chunks: Sequence[tuple[str, int, str]] = (),
    ) -> GraphExtractionResult: ...


class UnavailableGraphExtractionProvider:
    """Explicit fail-closed provider used until an approved provider is wired."""

    def extract(
        self,
        request: GraphExtractionRequest,
        source_chunks: Sequence[tuple[str, int, str]] = (),
    ) -> GraphExtractionResult:
        del request, source_chunks
        raise GraphExtractionUnavailable(
            "No GraphRAG extraction provider is configured; navigation remains available"
        )


class GraphExtractionOperator:
    """Controller-facing wrapper that validates provider output boundaries."""

    def __init__(self, provider: GraphExtractionProvider | None = None) -> None:
        self.provider = provider or UnavailableGraphExtractionProvider()

    def run(
        self,
        request: GraphExtractionRequest,
        source_chunks: Sequence[tuple[str, int, str]] = (),
    ) -> GraphExtractionResult:
        result = self.provider.extract(request, source_chunks)
        if result.project_id != request.project_id or result.paper_id != request.paper_id:
            raise ValueError("graph extraction result is outside the requested project or paper")
        if result.schema_version != request.schema_version:
            raise ValueError("graph extraction schema version does not match the request")
        if result.mode is not request.mode:
            raise ValueError("graph extraction mode does not match the request")
        if result.source_status != "model_generated_unverified":
            raise ValueError("graph extraction may not claim verified source status")
        return result

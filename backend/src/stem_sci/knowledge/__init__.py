"""Read-only shared-corpus retrieval and graph-navigation primitives.

This package deliberately separates retrieval navigation from research evidence.
Graph triples may nominate papers, while only traceable source excerpts may be
used in a ContextBundle.
"""

from .models import (
    ContextMode,
    CorpusManifest,
    CorpusReadiness,
    HybridContextBuildRequest,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
    RetrievalStrategy,
    SharedCorpusSummary,
)
from .graph_schema import (
    GraphEntityType,
    GraphExtractionMode,
    GraphExtractionRequest,
    GraphExtractionResult,
    GraphRelationType,
    GraphTriple,
)
from .service import HybridKnowledgeService

__all__ = [
    "ContextMode",
    "CorpusManifest",
    "CorpusReadiness",
    "HybridContextBuildRequest",
    "HybridKnowledgeService",
    "RetrievalSearchRequest",
    "RetrievalSearchResponse",
    "RetrievalStrategy",
    "SharedCorpusSummary",
    "GraphEntityType",
    "GraphExtractionMode",
    "GraphExtractionRequest",
    "GraphExtractionResult",
    "GraphRelationType",
    "GraphTriple",
]

"""Deterministic contracts for the optional GraphRAG extraction boundary."""

from pydantic import ValidationError
import pytest

from stem_sci.knowledge import (
    GraphEntityType,
    GraphExtractionMode,
    GraphExtractionResult,
    GraphRelationType,
    GraphTriple,
)


def _triple(**overrides: object) -> GraphTriple:
    values: dict[str, object] = {
        "project_id": "physics-demo",
        "paper_id": "paper-001",
        "head": "project-based learning",
        "head_type": GraphEntityType.PAPER,
        "relation": GraphRelationType.ADOPTS_PEDAGOGY,
        "tail": "project-based learning",
        "tail_type": GraphEntityType.PEDAGOGICAL_METHOD,
        "evidence": "The intervention used project-based learning.",
    }
    values.update(overrides)
    return GraphTriple(**values)


def test_graph_triple_is_unverified_and_traceable() -> None:
    triple = _triple(source_chunk_id="chunk-001", source_chunk_index=2)
    assert triple.source_status == "model_generated_unverified"
    assert triple.source_chunk_id == "chunk-001"


def test_paper_level_relation_requires_paper_head() -> None:
    with pytest.raises(ValidationError, match="requires a Paper head"):
        _triple(head_type=GraphEntityType.PEDAGOGICAL_METHOD)


def test_open_vocabulary_items_require_suggestion() -> None:
    with pytest.raises(ValidationError, match="new_type_suggestion"):
        _triple(
            relation=GraphRelationType.RELATED_TO,
            head_type=GraphEntityType.CONCEPT,
        )


def test_extraction_result_rejects_cross_paper_triples() -> None:
    with pytest.raises(ValidationError, match="project and paper"):
        GraphExtractionResult(
            extraction_id="extract-001",
            project_id="physics-demo",
            paper_id="paper-001",
            schema_version="graph-v1",
            mode=GraphExtractionMode.PROFILE,
            triples=[_triple(paper_id="paper-002")],
        )

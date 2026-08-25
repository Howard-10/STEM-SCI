"""Boundary tests for the optional GraphRAG extraction operator."""

import pytest

from stem_sci.knowledge import (
    GraphEntityType,
    GraphExtractionOperator,
    GraphExtractionRequest,
    GraphExtractionResult,
    GraphExtractionUnavailable,
    GraphRelationType,
    GraphTriple,
)


def _request() -> GraphExtractionRequest:
    return GraphExtractionRequest(
        project_id="physics-demo",
        paper_id="paper-001",
        title="Physics modelling with scaffolding",
        schema_version="graph-v1",
    )


def _result(request: GraphExtractionRequest, **overrides: object) -> GraphExtractionResult:
    result_project_id = str(overrides.get("project_id", request.project_id))
    values: dict[str, object] = {
        "extraction_id": "extract-001",
            "project_id": result_project_id,
        "paper_id": request.paper_id,
        "schema_version": request.schema_version,
        "mode": request.mode,
        "triples": [
            GraphTriple(
                project_id=result_project_id,
                paper_id=request.paper_id,
                head="paper-001",
                head_type=GraphEntityType.PAPER,
                relation=GraphRelationType.STUDIES_DOMAIN,
                tail="physics",
                tail_type=GraphEntityType.SUBJECT_DOMAIN,
                evidence="The paper studies physics modelling.",
            )
        ],
    }
    values.update(overrides)
    return GraphExtractionResult(**values)


def test_default_provider_fails_closed() -> None:
    with pytest.raises(GraphExtractionUnavailable, match="No GraphRAG extraction provider"):
        GraphExtractionOperator().run(_request())


def test_operator_accepts_matching_unverified_candidate() -> None:
    request = _request()

    class Provider:
        def extract(self, request: GraphExtractionRequest, source_chunks=()):
            return _result(request)

    result = GraphExtractionOperator(Provider()).run(request)
    assert result.source_status == "model_generated_unverified"


def test_operator_rejects_cross_scope_candidate() -> None:
    request = _request()

    class Provider:
        def extract(self, request: GraphExtractionRequest, source_chunks=()):
            return _result(request, project_id="other-project")

    with pytest.raises(ValueError, match="outside the requested project"):
        GraphExtractionOperator(Provider()).run(request)

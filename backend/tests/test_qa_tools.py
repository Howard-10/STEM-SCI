from __future__ import annotations

from stem_sci.knowledge.qa_tools import QAToolExecutor, tool_definitions


def test_tool_definitions_expose_bounded_read_only_capabilities() -> None:
    names = [item["function"]["name"] for item in tool_definitions()]

    assert names == [
        "graph_search",
        "vector_search",
        "hybrid_search",
        "paper_lookup",
        "workflow_agent",
        "external_paper_search",
    ]
    assert all(
        item["function"]["parameters"]["additionalProperties"] is False
        for item in tool_definitions()
    )


def test_external_search_is_explicitly_fail_closed() -> None:
    result = QAToolExecutor(object()).execute(
        name="external_paper_search",
        arguments={"query": "graph rag"},
        project_id="demo",
        default_query="graph rag",
    )

    assert result["status"] == "NOT_CONFIGURED"
    assert "external_search_not_configured" in result["risk_flags"]


def test_workflow_tool_is_proposal_only() -> None:
    result = QAToolExecutor(object()).execute(
        name="workflow_agent",
        arguments={"agent": "EvidenceReviewAgent", "task": "review sources"},
        project_id="demo",
        default_query="review sources",
    )

    assert result["mode"] == "proposal_only"
    assert "does not create" in result["message"]

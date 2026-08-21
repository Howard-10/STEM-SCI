"""Read-only tools exposed to the conversational GraphRAG router."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import ContextMode, RetrievalSearchRequest
from .service import HybridKnowledgeService


TOOL_NAMES = (
    "graph_search",
    "vector_search",
    "hybrid_search",
    "paper_lookup",
    "workflow_agent",
    "external_paper_search",
)


def tool_definitions() -> list[dict[str, Any]]:
    """Return OpenAI-compatible function definitions with strict arguments."""

    query_tool = {
        "type": "function",
        "function": {
            "name": "hybrid_search",
            "description": (
                "Search the STEM-SCI paper corpus using graph navigation plus "
                "dense and BM25 text retrieval. Use this for evidence-based questions."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 12},
                },
                "required": ["query"],
            },
        },
    }
    graph_tool = _clone_tool(
        query_tool,
        name="graph_search",
        description=(
            "Navigate the paper graph to find related candidate papers. Graph "
            "relations are navigation hints and are never formal evidence."
        ),
    )
    vector_tool = _clone_tool(
        query_tool,
        name="vector_search",
        description=(
            "Search original paper chunks with dense and sparse retrieval. "
            "Use this when the user needs textual evidence."
        ),
    )
    paper_tool = {
        "type": "function",
        "function": {
            "name": "paper_lookup",
            "description": "Locate a specific paper by title, DOI, filename, or paper identifier.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 12},
                },
                "required": ["query"],
            },
        },
    }
    workflow_tool = {
        "type": "function",
        "function": {
            "name": "workflow_agent",
            "description": (
                "Recommend one of the six research workflow Agents for a task. "
                "This tool is proposal-only and never changes workflow state."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "agent": {
                        "type": "string",
                        "enum": [
                            "MentorPlanningAgent",
                            "EvidenceReviewAgent",
                            "ResearchDesignAgent",
                            "DataAnalysisAgent",
                            "PaperWritingAgent",
                            "IndependentReviewAgent",
                        ],
                    },
                    "task": {"type": "string", "minLength": 1},
                },
                "required": ["agent", "task"],
            },
        },
    }
    external_tool = {
        "type": "function",
        "function": {
            "name": "external_paper_search",
            "description": (
                "Request a search outside the local corpus. This deployment "
                "does not perform external network search unless explicitly configured."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["query"],
            },
        },
    }
    return [graph_tool, vector_tool, query_tool, paper_tool, workflow_tool, external_tool]


class QAToolExecutor:
    """Execute conversational tools without mutating workflow state."""

    def __init__(self, knowledge_service: HybridKnowledgeService) -> None:
        self._knowledge_service = knowledge_service

    def execute(
        self,
        *,
        name: str,
        arguments: Mapping[str, Any],
        project_id: str,
        default_query: str,
    ) -> dict[str, Any]:
        if name in {"graph_search", "vector_search", "hybrid_search", "paper_lookup"}:
            query = str(arguments.get("query") or default_query).strip()
            if not query:
                return {"ok": False, "error": "query is required"}
            limit = _bounded_int(arguments.get("limit"), default=8, maximum=12)
            response = self._knowledge_service.search(
                RetrievalSearchRequest(
                    project_id=project_id,
                    corpus_ids=["physics_stem_v1"],
                    query=query,
                    mode=ContextMode.DISCOVERY,
                    limit=limit,
                )
            )
            payload = response.model_dump(mode="json")
            payload["retrieval_response"] = response.model_dump(mode="json")
            if name == "graph_search":
                payload = {
                    "project_id": project_id,
                    "corpus_id": response.corpus_id,
                    "retrieval_status": response.retrieval_status,
                    "candidate_papers": [
                        item.model_dump(mode="json") for item in response.candidate_papers
                    ],
                    "risk_flags": [
                        *response.risk_flags,
                        "graph_relations_are_navigation_only",
                    ],
                    "retrieval_trace": response.retrieval_trace.model_dump(mode="json"),
                    "retrieval_response": response.model_dump(mode="json"),
                }
            elif name == "vector_search":
                payload = {
                    "project_id": project_id,
                    "corpus_id": response.corpus_id,
                    "retrieval_status": response.retrieval_status,
                    "chunk_hits": [
                        item.model_dump(mode="json") for item in response.chunk_hits
                    ],
                    "risk_flags": response.risk_flags,
                    "retrieval_response": response.model_dump(mode="json"),
                }
            elif name == "paper_lookup":
                payload = {
                    "project_id": project_id,
                    "corpus_id": response.corpus_id,
                    "retrieval_status": response.retrieval_status,
                    "papers": [
                        item.model_dump(mode="json") for item in response.candidate_papers
                    ],
                    "matching_chunks": [
                        item.model_dump(mode="json") for item in response.chunk_hits
                    ],
                    "risk_flags": response.risk_flags,
                    "retrieval_response": response.model_dump(mode="json"),
                }
            return payload

        if name == "workflow_agent":
            agent = str(arguments.get("agent") or "MentorPlanningAgent")
            task = str(arguments.get("task") or default_query).strip()
            return {
                "ok": True,
                "mode": "proposal_only",
                "agent": agent,
                "task": task,
                "message": (
                    "The conversational endpoint can recommend an Agent, but it "
                    "does not create, approve, or advance a workflow project. "
                    "Use the workflow API for state-changing actions."
                ),
            }

        if name == "external_paper_search":
            return {
                "ok": False,
                "status": "NOT_CONFIGURED",
                "query": str(arguments.get("query") or default_query),
                "message": (
                    "External paper search is not configured for this deployment. "
                    "Only the declared local corpus was searched."
                ),
                "risk_flags": ["external_search_not_configured"],
            }

        return {"ok": False, "error": f"unknown tool: {name}"}


def _clone_tool(
    source: Mapping[str, Any],
    *,
    name: str,
    description: str,
) -> dict[str, Any]:
    function = dict(source["function"])
    function["name"] = name
    function["description"] = description
    return {"type": "function", "function": function}


def _bounded_int(value: Any, *, default: int, maximum: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(maximum, parsed))


def route_for_tool(name: str) -> str:
    """Map a tool call to the public QA route vocabulary."""

    if name in TOOL_NAMES:
        return name
    return "direct_answer"


def tool_reason(name: str) -> str:
    reasons = {
        "graph_search": "LLM selected graph navigation for candidate-paper discovery.",
        "vector_search": "LLM selected original-text retrieval for evidence.",
        "hybrid_search": "LLM selected graph-guided dense plus sparse retrieval.",
        "paper_lookup": "LLM selected a targeted paper lookup.",
        "workflow_agent": "LLM selected a proposal-only research workflow Agent.",
        "external_paper_search": "LLM requested external search, which is currently unavailable.",
    }
    return reasons.get(name, "LLM answered directly without a retrieval tool.")

"""Models for the user-facing QA chain."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class QAStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QAAnswerRequest(QAStrictModel):
    project_id: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1, max_length=20_000)
    conversation_id: str | None = Field(default=None, max_length=128)
    context_bundle_ref: str | None = Field(default=None, max_length=128)
    top_k: int = Field(default=8, ge=1, le=20)
    token_budget: int = Field(default=3000, ge=256, le=20_000)
    allow_llm: bool = True


class QAReference(QAStrictModel):
    paper_title: str
    source_filename: str
    canonical_paper_id: str
    canonical_chunk_id: str
    chunk_index: int
    excerpt: str
    normalized_doi: str | None = None
    source_type: Literal["chunk", "paper"] = "chunk"


class QARouteDecision(QAStrictModel):
    route: Literal[
        "hybrid_search",
        "graph_search",
        "vector_search",
        "paper_lookup",
        "workflow_agent",
        "external_paper_search",
        "direct_answer",
    ] = "hybrid_search"
    reason: str
    recommended_agent: str | None = None


class QAWorkflowAction(QAStrictModel):
    """A bounded workflow action reported by the conversational facade."""

    action: Literal[
        "STARTED",
        "STATUS",
        "NEXT_AGENT",
        "APPROVAL_READY",
        "PROPOSAL_ONLY",
        "UNAVAILABLE",
    ]
    project_id: str
    message: str
    current_stage: str | None = None
    selected_agent: str | None = None
    approval_required: bool = False
    confirmation_required: bool = False
    approval_request_id: str | None = None
    approval_request: dict[str, Any] | None = None
    workflow_state: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    next_available_actions: list[str] = Field(default_factory=list)


class QAAnswerRecord(QAStrictModel):
    answer: str
    citation_indices: list[int] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_follow_up: bool = False
    follow_up_question: str | None = None


class QAAnswerResponse(QAStrictModel):
    project_id: str
    conversation_id: str
    question: str
    rewritten_query: str
    route: QARouteDecision
    answer: str
    citations: list[QAReference] = Field(default_factory=list)
    retrieval_status: str
    retrieval_trace_ref: str | None = None
    context_bundle_ref: str | None = None
    memory_ref: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    answer_mode: Literal["llm", "fallback"] = "fallback"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_follow_up: bool = False
    follow_up_question: str | None = None
    tool_calls: list[str] = Field(default_factory=list)
    workflow_action: QAWorkflowAction | None = None


class MemoryTurn(QAStrictModel):
    memory_id: str
    conversation_id: str
    project_id: str
    question: str
    rewritten_query: str
    answer: str
    route: str
    citations: list[QAReference] = Field(default_factory=list)
    retrieval_trace_ref: str | None = None
    created_at: str

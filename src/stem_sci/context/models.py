"""Public contracts for per-call context assembly."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from stem_sci.compat.langchain import BaseMessage
from stem_sci.memory.models import MemoryRecord


class RuntimeContext(BaseModel):
    """Invocation identity and permissions; never included in prompts by default."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    user_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    locale: str = "zh-CN"
    permissions: frozenset[str] = frozenset()


class ApprovedDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    decision_id: str
    content: str = Field(min_length=1, max_length=8_000)


class EvidenceContext(BaseModel):
    """Read-only projection of a RAG result; no knowledge-store payload is copied."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: str
    source: str
    content: str = Field(min_length=1, max_length=20_000)
    citation: str = ""
    confidence: float | None = Field(default=None, ge=0, le=1)
    relevance: float = Field(default=0.0, ge=0, le=1)


class TokenBudget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    model_context_window: int = Field(default=65_536, ge=2_048)
    max_output_tokens: int = Field(default=4_096, ge=1)
    safety_reserve_tokens: int = Field(default=2_048, ge=0)
    max_input_tokens: int | None = Field(default=16_000, ge=512)

    @property
    def input_limit(self) -> int:
        provider_limit = (
            self.model_context_window - self.max_output_tokens - self.safety_reserve_tokens
        )
        if provider_limit < 1:
            raise ValueError("Output and safety reservations exhaust the model context window")
        return min(provider_limit, self.max_input_tokens or provider_limit)


class ContextRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")
    identity: RuntimeContext
    task: str = Field(min_length=1, max_length=12_000)
    user_message: str = Field(min_length=1, max_length=100_000)
    output_requirements: str = "Answer concisely with explicit uncertainty and source references."
    forbidden_operations: tuple[str, ...] = ()
    approved_decisions: list[ApprovedDecision] = Field(default_factory=list)
    conversation_summary: str = ""
    recent_messages: list[BaseMessage] = Field(default_factory=list)
    memories: list[MemoryRecord] = Field(default_factory=list)
    evidence: list[EvidenceContext] = Field(default_factory=list)
    budget: TokenBudget = Field(default_factory=TokenBudget)
    prompt_version: str = "1.0.0"


class ContextTrace(BaseModel):
    model_config = ConfigDict(frozen=True)
    user_id: str
    project_id: str
    thread_id: str
    run_id: str
    selected_memory_ids: tuple[str, ...] = ()
    selected_evidence_ids: tuple[str, ...] = ()
    included_message_ids: tuple[str, ...] = ()
    dropped: tuple[str, ...] = ()
    prompt_hashes: dict[str, str] = Field(default_factory=dict)
    estimated_input_tokens: int
    input_token_limit: int


class ContextPackage(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)
    messages: list[BaseMessage]
    trace: ContextTrace


def evidence_from_rag(result: dict[str, Any], index: int = 0) -> EvidenceContext:
    """Normalize one existing vector/graph result without changing the RAG implementation."""

    evidence_id = str(
        result.get("evidence_id")
        or result.get("chunk_id")
        or result.get("paper_id")
        or result.get("doi")
        or f"rag_{index}"
    )
    content = str(result.get("text") or result.get("evidence") or result.get("content") or "")
    if not content:
        raise ValueError("RAG result contains no evidence text")
    citation = str(result.get("doi") or result.get("paper_title") or result.get("source") or "")
    confidence = result.get("confidence")
    return EvidenceContext(
        evidence_id=evidence_id,
        source=str(result.get("source_type") or result.get("relation") or "rag"),
        content=content,
        citation=citation,
        confidence=float(confidence) if confidence is not None else None,
        relevance=float(result.get("relevance") or result.get("score") or 0.0),
    )

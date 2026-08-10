"""Rule-based budget accounting for Controller runs."""

from __future__ import annotations

import os

from pydantic import Field

from stem_sci.core.models import DomainModel


class BudgetState(DomainModel):
    max_llm_calls: int = Field(default=0, ge=0)
    used_llm_calls: int = Field(default=0, ge=0)
    max_retrieval_calls: int = Field(default=20, ge=0)
    used_retrieval_calls: int = Field(default=0, ge=0)
    max_code_retries: int = Field(default=3, ge=0)
    used_code_retries: int = Field(default=0, ge=0)
    max_review_rounds: int = Field(default=3, ge=0)
    used_review_rounds: int = Field(default=0, ge=0)
    max_execution_seconds: int = Field(default=600, ge=0)
    used_execution_seconds: int = Field(default=0, ge=0)


class BudgetManager:
    def __init__(self, state: BudgetState | None = None) -> None:
        self.state = state or BudgetState(max_llm_calls=_configured_max_llm_calls())

    def can_use_llm(self, count: int = 1) -> bool:
        return self.state.used_llm_calls + count <= self.state.max_llm_calls

    def consume_llm(self, count: int = 1) -> BudgetState:
        if count < 0 or not self.can_use_llm(count):
            raise ValueError("llm budget exceeded")
        self.state = self.state.model_copy(
            update={"used_llm_calls": self.state.used_llm_calls + count}
        )
        return self.state

    def can_retrieve(self, count: int = 1) -> bool:
        return self.state.used_retrieval_calls + count <= self.state.max_retrieval_calls

    def consume_retrieval(self, count: int = 1) -> BudgetState:
        if count < 0 or not self.can_retrieve(count):
            raise ValueError("retrieval budget exceeded")
        self.state = self.state.model_copy(
            update={"used_retrieval_calls": self.state.used_retrieval_calls + count}
        )
        return self.state


def _configured_max_llm_calls() -> int:
    raw_limit = os.getenv("STEM_SCI_MAX_LLM_CALLS", "0")
    try:
        limit = int(raw_limit)
    except ValueError:
        raise ValueError("STEM_SCI_MAX_LLM_CALLS must be a non-negative integer") from None
    if limit < 0:
        raise ValueError("STEM_SCI_MAX_LLM_CALLS must be a non-negative integer")
    return limit

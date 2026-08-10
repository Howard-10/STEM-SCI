"""OpenAI-compatible model configuration for context and memory tasks."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from pydantic import SecretStr


@dataclass(frozen=True)
class ContextModelConfig:
    """Credentials remain in environment variables and are never included in traces."""

    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    temperature: float = 0.0
    max_retries: int = 2

    @classmethod
    def from_env(cls) -> ContextModelConfig:
        api_key = os.getenv("STEM_CONTEXT_LLM_API_KEY") or os.getenv("STEM_KB_LLM_API_KEY", "")
        if not api_key:
            raise ValueError("STEM_CONTEXT_LLM_API_KEY is required for live model evaluation")
        return cls(
            api_key=api_key,
            base_url=os.getenv("STEM_CONTEXT_LLM_BASE_URL", "https://api.deepseek.com"),
            model=os.getenv("STEM_CONTEXT_LLM_MODEL", "deepseek-v4-flash"),
        )

    def create_chat_model(self) -> Any:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "Install the langchain-openai dependency for live model calls"
            ) from exc
        return ChatOpenAI(
            api_key=SecretStr(self.api_key),
            base_url=self.base_url,
            model=self.model,
            temperature=self.temperature,
            max_retries=self.max_retries,
        )

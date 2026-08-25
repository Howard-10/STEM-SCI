"""Bounded retry coordination for structured LLM providers."""

from __future__ import annotations

from pydantic import BaseModel

from .provider import GenerationResult, LLMProvider, LLMProviderError


class StructuredGenerationError(RuntimeError):
    """Structured generation failed after the configured attempts."""

    def __init__(self, message: str, *, provider_error: LLMProviderError) -> None:
        super().__init__(message)
        self.provider_error = provider_error


class StructuredGenerator:
    """Retry typed provider failures without retaining raw response content."""

    def __init__(self, provider: LLMProvider, max_retries: int = 1) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        self.provider = provider
        self.max_retries = max_retries

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
        model: str,
        prompt_version: str,
    ) -> GenerationResult:
        last_error: LLMProviderError | None = None
        for retry_count in range(self.max_retries + 1):
            try:
                result = self.provider.generate_structured(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_model=response_model,
                    model=model,
                    prompt_version=prompt_version,
                )
            except LLMProviderError as error:
                last_error = error
                continue
            return result.model_copy(update={"retry_count": retry_count})
        if last_error is None:
            raise RuntimeError("structured generation exhausted without a provider error")
        raise StructuredGenerationError(
            f"structured generation failed after {self.max_retries + 1} attempts",
            provider_error=last_error,
        ) from last_error

"""Provider contracts for audit-safe structured LLM generation."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from time import perf_counter
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, SerializeAsAny, ValidationError

from stem_sci.utils.hash_utils import sha256_text
from stem_sci.utils.ids import new_id


class GenerationResult(BaseModel):
    """Validated output plus non-content metadata needed for provenance."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    parsed_output: SerializeAsAny[BaseModel]
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)
    response_hash: str = Field(min_length=64, max_length=64)
    retry_count: int = Field(default=0, ge=0)


class LLMProviderError(RuntimeError):
    """Base class for failures safe to expose to runtime callers."""


class LLMTransportError(LLMProviderError):
    """The configured provider could not be reached."""


class LLMResponseError(LLMProviderError):
    """The provider returned an unusable protocol response."""


class LLMSchemaError(LLMProviderError):
    """The provider response did not satisfy the requested schema."""


class LLMProvider(Protocol):
    """One structured generation call, independent of agent semantics."""

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
        model: str,
        prompt_version: str,
    ) -> GenerationResult: ...


class GPTProvider:
    """GPT-compatible chat-completions provider using JSON Schema output."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 60.0,
        default_model: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("LLM base URL must not be empty")
        if not api_key:
            raise ValueError("LLM API key must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("LLM timeout must be greater than zero")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.default_model = default_model
        self._client = client or httpx.Client(timeout=timeout_seconds)

    @classmethod
    def from_env(cls) -> GPTProvider:
        """Build a GPT provider without exposing configuration values in errors."""

        provider_name = os.getenv("STEM_SCI_LLM_PROVIDER", "gpt").strip().lower()
        if provider_name != "gpt":
            raise ValueError("unsupported STEM_SCI_LLM_PROVIDER")
        base_url = _required_environment_value("STEM_SCI_LLM_BASE_URL")
        api_key = _required_environment_value("STEM_SCI_LLM_API_KEY")
        default_model = _required_environment_value("STEM_SCI_LLM_MODEL")
        timeout_raw = os.getenv("STEM_SCI_LLM_TIMEOUT_SECONDS", "60")
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError:
            raise ValueError("STEM_SCI_LLM_TIMEOUT_SECONDS must be numeric") from None
        return cls(
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            default_model=default_model,
        )

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
        model: str,
        prompt_version: str,
    ) -> GenerationResult:
        selected_model = model or self.default_model
        if not selected_model:
            raise LLMResponseError("LLM model must not be empty")
        request_body = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "strict": True,
                    "schema": response_model.model_json_schema(),
                },
            },
        }
        started = perf_counter()
        try:
            response = self._client.post(
                self._chat_completions_url(),
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=request_body,
                timeout=self.timeout_seconds,
            )
        except httpx.RequestError:
            raise LLMTransportError("LLM provider request failed") from None
        latency_ms = max(0, round((perf_counter() - started) * 1000))
        if not response.is_success:
            raise LLMResponseError(
                f"LLM provider returned HTTP status {response.status_code}"
            ) from None

        response_hash = sha256_text(response.text)
        payload = _response_payload(response)
        parsed_output = _parse_chat_output(payload, response_model)
        usage = payload.get("usage")
        usage_mapping = usage if isinstance(usage, Mapping) else {}
        request_id = _string_or_none(payload.get("id")) or response.headers.get("x-request-id")
        return GenerationResult(
            parsed_output=parsed_output,
            model=selected_model,
            prompt_version=prompt_version,
            request_id=request_id or new_id("llm-request"),
            input_tokens=_nonnegative_int_or_none(usage_mapping.get("prompt_tokens")),
            output_tokens=_nonnegative_int_or_none(usage_mapping.get("completion_tokens")),
            latency_ms=latency_ms,
            response_hash=response_hash,
        )

    def _chat_completions_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"


class FakeLLMProvider:
    """Deterministic structured provider for offline tests and CI."""

    def __init__(self, responses: Sequence[Mapping[str, Any] | BaseModel]) -> None:
        self._responses = list(responses)
        self.call_count = 0

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
        model: str,
        prompt_version: str,
    ) -> GenerationResult:
        del system_prompt, user_prompt
        response_index = self.call_count
        self.call_count += 1
        if response_index >= len(self._responses):
            raise LLMResponseError("fake LLM response queue exhausted")
        payload = self._responses[response_index]
        raw_payload = payload.model_dump() if isinstance(payload, BaseModel) else dict(payload)
        try:
            parsed_output = response_model.model_validate(raw_payload)
        except ValidationError:
            raise LLMSchemaError("LLM structured response failed schema validation") from None
        json_payload = parsed_output.model_dump(mode="json")
        response_text = json.dumps(
            json_payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        return GenerationResult(
            parsed_output=parsed_output,
            model=model,
            prompt_version=prompt_version,
            request_id=f"fake-llm-request-{self.call_count}",
            response_hash=sha256_text(response_text),
        )


def _required_environment_value(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ValueError(f"{name} is required")
    return value


def _response_payload(response: httpx.Response) -> Mapping[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        raise LLMResponseError("LLM provider returned invalid JSON") from None
    if not isinstance(payload, Mapping):
        raise LLMResponseError("LLM provider returned an invalid response shape")
    return payload


def _parse_chat_output(
    payload: Mapping[str, Any], response_model: type[BaseModel]
) -> BaseModel:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        raise LLMResponseError("LLM provider returned an invalid response shape")
    message = choices[0].get("message")
    if not isinstance(message, Mapping):
        raise LLMResponseError("LLM provider returned an invalid response shape")
    structured_content = message.get("parsed", message.get("content"))
    if isinstance(structured_content, str):
        try:
            structured_content = json.loads(structured_content)
        except json.JSONDecodeError:
            raise LLMResponseError("LLM provider returned invalid structured JSON") from None
    if not isinstance(structured_content, Mapping):
        raise LLMResponseError("LLM provider returned an invalid structured response")
    try:
        return response_model.model_validate(structured_content)
    except ValidationError:
        raise LLMSchemaError("LLM structured response failed schema validation") from None


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _nonnegative_int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None

"""Provider contracts for audit-safe structured LLM generation."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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


@dataclass(frozen=True)
class ChatToolCall:
    """A provider-neutral function call emitted by a chat completion."""

    call_id: str
    name: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True)
class ChatCompletionResult:
    """The bounded chat result needed by the tool-routing layer."""

    message: Mapping[str, Any]
    content: str | None
    tool_calls: tuple[ChatToolCall, ...]
    response_hash: str
    request_id: str


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
        self.response_format_mode = _response_format_mode(self.base_url)

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
            "response_format": _response_format(
                response_model,
                self.response_format_mode,
            ),
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

    def complete(
        self,
        *,
        messages: Sequence[Mapping[str, Any]],
        model: str,
        tools: Sequence[Mapping[str, Any]] = (),
        tool_choice: str | Mapping[str, Any] | None = None,
        response_model: type[BaseModel] | None = None,
    ) -> ChatCompletionResult:
        """Run a chat completion for bounded LLM tool routing.

        This method intentionally returns only the assistant message and parsed
        function calls. The caller owns tool execution and must append tool
        results explicitly before requesting the final answer.
        """

        selected_model = model or self.default_model
        if not selected_model:
            raise LLMResponseError("LLM model must not be empty")
        request_body: dict[str, Any] = {
            "model": selected_model,
            "messages": list(messages),
        }
        if tools:
            request_body["tools"] = list(tools)
            request_body["tool_choice"] = tool_choice or "auto"
        if response_model is not None:
            request_body["response_format"] = _response_format(
                response_model,
                self.response_format_mode,
            )
        try:
            response = self._client.post(
                self._chat_completions_url(),
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=request_body,
                timeout=self.timeout_seconds,
            )
        except httpx.RequestError:
            raise LLMTransportError("LLM provider request failed") from None
        if not response.is_success:
            raise LLMResponseError(
                f"LLM provider returned HTTP status {response.status_code}"
            ) from None
        payload = _response_payload(response)
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            raise LLMResponseError("LLM provider returned an invalid response shape")
        message = choices[0].get("message")
        if not isinstance(message, Mapping):
            raise LLMResponseError("LLM provider returned an invalid response shape")
        return _chat_completion_result(response, message)

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


def _response_format_mode(base_url: str) -> str:
    """Select a provider-compatible JSON response mode.

    ``auto`` uses JSON mode for DeepSeek-compatible endpoints because some
    deployments do not accept OpenAI's strict json_schema envelope. Set
    ``STEM_SCI_LLM_RESPONSE_FORMAT=json_schema`` or ``json_object`` to
    override this behavior.
    """

    configured = os.getenv("STEM_SCI_LLM_RESPONSE_FORMAT", "auto").strip().lower()
    if configured in {"json_schema", "json_object"}:
        return configured
    if "deepseek.com" in base_url.casefold():
        return "json_object"
    return "json_schema"


def _response_format(response_model: type[BaseModel], mode: str) -> Mapping[str, Any]:
    if mode == "json_object":
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": response_model.__name__,
            "strict": True,
            "schema": response_model.model_json_schema(),
        },
    }


def _response_payload(response: httpx.Response) -> Mapping[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        raise LLMResponseError("LLM provider returned invalid JSON") from None
    if not isinstance(payload, Mapping):
        raise LLMResponseError("LLM provider returned an invalid response shape")
    return payload


def _chat_completion_result(
    response: httpx.Response,
    message: Mapping[str, Any],
) -> ChatCompletionResult:
    raw_tool_calls = message.get("tool_calls")
    parsed_tool_calls: list[ChatToolCall] = []
    if raw_tool_calls is not None:
        if not isinstance(raw_tool_calls, list):
            raise LLMResponseError("LLM provider returned invalid tool calls")
        for raw_call in raw_tool_calls:
            if not isinstance(raw_call, Mapping):
                raise LLMResponseError("LLM provider returned invalid tool call")
            function = raw_call.get("function")
            if not isinstance(function, Mapping):
                raise LLMResponseError("LLM provider returned invalid tool call")
            call_id = raw_call.get("id")
            name = function.get("name")
            arguments = function.get("arguments", "{}")
            if not isinstance(call_id, str) or not call_id:
                raise LLMResponseError("LLM provider returned a tool call without an id")
            if not isinstance(name, str) or not name:
                raise LLMResponseError("LLM provider returned a tool call without a name")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    raise LLMResponseError("LLM provider returned invalid tool arguments") from None
            if not isinstance(arguments, Mapping):
                raise LLMResponseError("LLM provider returned invalid tool arguments")
            parsed_tool_calls.append(
                ChatToolCall(
                    call_id=call_id,
                    name=name,
                    arguments=dict(arguments),
                )
            )
    content = message.get("content")
    if content is not None and not isinstance(content, str):
        raise LLMResponseError("LLM provider returned invalid message content")
    return ChatCompletionResult(
        message=dict(message),
        content=content,
        tool_calls=tuple(parsed_tool_calls),
        response_hash=sha256_text(response.text),
        request_id=(
            _string_or_none(response.headers.get("x-request-id"))
            or f"chat-request-{sha256_text(response.text)[:16]}"
        ),
    )


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

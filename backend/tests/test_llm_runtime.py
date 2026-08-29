"""Tests for structured LLM generation and its audit-safe runtime contracts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from stem_sci.agents.runtime import (
    FakeLLMProvider,
    GPTProvider,
    LLMSchemaError,
    LLMTransportError,
    PromptRegistry,
    StructuredGenerationError,
    StructuredGenerator,
)
from stem_sci.controller.budget.budget_manager import BudgetManager, BudgetState
from stem_sci.provenance.models import AgentRunRecord


class ValueModel(BaseModel):
    value: str


def test_structured_generator_parses_fake_gpt_response() -> None:
    provider = FakeLLMProvider(responses=[{"value": "ok"}])

    result = StructuredGenerator(provider).generate(
        system_prompt="Return JSON.",
        user_prompt="value",
        response_model=ValueModel,
        model="gpt-test",
        prompt_version="test-v1",
    )

    assert result.parsed_output.value == "ok"
    assert result.retry_count == 0
    assert provider.call_count == 1
    assert len(result.response_hash) == 64
    assert result.model_dump()["parsed_output"] == {"value": "ok"}


def test_budget_rejects_llm_call_after_limit() -> None:
    budget = BudgetManager(BudgetState(max_llm_calls=1))

    assert budget.can_use_llm()
    assert budget.consume_llm().used_llm_calls == 1
    assert not budget.can_use_llm()
    with pytest.raises(ValueError, match="llm budget exceeded"):
        budget.consume_llm()


def test_invalid_structured_response_is_retried_then_fails() -> None:
    provider = FakeLLMProvider(responses=[{"bad": True}, {"bad": True}])

    with pytest.raises(StructuredGenerationError, match="structured generation failed"):
        StructuredGenerator(provider, max_retries=1).generate(
            system_prompt="Return JSON.",
            user_prompt="value",
            response_model=ValueModel,
            model="gpt-test",
            prompt_version="test-v1",
        )

    assert provider.call_count == 2


def test_structured_generator_preserves_typed_terminal_failure() -> None:
    provider = FakeLLMProvider(responses=[{"bad": True}])

    with pytest.raises(StructuredGenerationError) as error:
        StructuredGenerator(provider, max_retries=0).generate(
            system_prompt="Return JSON.",
            user_prompt="value",
            response_model=ValueModel,
            model="gpt-test",
            prompt_version="test-v1",
        )

    assert isinstance(error.value.provider_error, LLMSchemaError)
    assert error.value.__cause__ is error.value.provider_error


def test_structured_generator_records_retry_count_on_recovery() -> None:
    provider = FakeLLMProvider(responses=[{"bad": True}, {"value": "recovered"}])

    result = StructuredGenerator(provider, max_retries=1).generate(
        system_prompt="Return JSON.",
        user_prompt="value",
        response_model=ValueModel,
        model="gpt-test",
        prompt_version="test-v1",
    )

    assert result.parsed_output.value == "recovered"
    assert result.retry_count == 1


def test_fake_provider_hashes_valid_pydantic_datetime_output() -> None:
    class TimestampModel(BaseModel):
        observed_at: datetime

    response = TimestampModel(observed_at=datetime(2026, 8, 5, tzinfo=UTC))

    result = StructuredGenerator(FakeLLMProvider(responses=[response])).generate(
        system_prompt="Return JSON.",
        user_prompt="timestamp",
        response_model=TimestampModel,
        model="gpt-test",
        prompt_version="test-v1",
    )

    assert result.parsed_output.observed_at == response.observed_at
    assert len(result.response_hash) == 64


def test_gpt_provider_requests_json_schema_and_parses_chat_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STEM_SCI_LLM_RESPONSE_FORMAT", raising=False)
    request_body: dict[str, Any] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        request_body.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "request-123",
                "choices": [{"message": {"content": '{"value":"ok"}'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handle))
    provider = GPTProvider(
        base_url="https://gpt.invalid/v1",
        api_key="redacted",
        client=client,
    )

    result = provider.generate_structured(
        system_prompt="Return JSON.",
        user_prompt="value",
        response_model=ValueModel,
        model="gpt-test",
        prompt_version="test-v1",
    )

    assert result.parsed_output.value == "ok"
    assert result.request_id == "request-123"
    assert result.input_tokens == 12
    assert result.output_tokens == 3
    assert request_body["response_format"]["type"] == "json_schema"
    assert request_body["response_format"]["json_schema"]["strict"] is True


def test_gpt_provider_raises_typed_schema_error_without_response_content() -> None:
    response_marker = "response-content-marker"

    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": f'{{"other":"{response_marker}"}}'}}]},
        )

    provider = GPTProvider(
        base_url="https://gpt.invalid/v1",
        api_key="redacted",
        client=httpx.Client(transport=httpx.MockTransport(handle)),
    )

    with pytest.raises(LLMSchemaError) as error:
        provider.generate_structured(
            system_prompt="Return JSON.",
            user_prompt="value",
            response_model=ValueModel,
            model="gpt-test",
            prompt_version="test-v1",
        )

    assert response_marker not in str(error.value)


def test_gpt_provider_redacts_request_details_from_transport_error() -> None:
    prompt_marker = "full-prompt-marker"
    credential_marker = "credential-marker"

    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unavailable", request=request)

    provider = GPTProvider(
        base_url="https://gpt.invalid/v1",
        api_key=credential_marker,
        client=httpx.Client(transport=httpx.MockTransport(fail)),
    )

    with pytest.raises(LLMTransportError) as error:
        provider.generate_structured(
            system_prompt=prompt_marker,
            user_prompt=prompt_marker,
            response_model=ValueModel,
            model="gpt-test",
            prompt_version="test-v1",
        )

    message = str(error.value)
    assert prompt_marker not in message
    assert credential_marker not in message


def test_runtime_configuration_comes_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STEM_SCI_LLM_PROVIDER", "gpt")
    monkeypatch.setenv("STEM_SCI_LLM_BASE_URL", "https://gpt.invalid/v1")
    monkeypatch.setenv("STEM_SCI_LLM_API_KEY", "redacted")
    monkeypatch.setenv("STEM_SCI_LLM_MODEL", "gpt-test")
    monkeypatch.setenv("STEM_SCI_LLM_TIMEOUT_SECONDS", "7.5")
    monkeypatch.setenv("STEM_SCI_MAX_LLM_CALLS", "4")

    provider = GPTProvider.from_env()
    budget = BudgetManager()

    assert provider.default_model == "gpt-test"
    assert provider.timeout_seconds == 7.5
    assert budget.state.max_llm_calls == 4


def test_prompt_registry_versions_and_renders_prompts() -> None:
    registry = PromptRegistry()
    registry.register(
        name="value",
        version="value-v1",
        system_prompt="Return structured JSON.",
        user_prompt_template="Extract {field} from {source}.",
    )

    system_prompt, user_prompt = registry.render(
        "value", "value-v1", field="value", source="the bounded corpus"
    )

    assert system_prompt == "Return structured JSON."
    assert user_prompt == "Extract value from the bounded corpus."
    with pytest.raises(ValueError, match="already registered"):
        registry.register(
            name="value",
            version="value-v1",
            system_prompt="Different prompt.",
            user_prompt_template="Different {field}.",
        )


def test_agent_run_record_stores_only_llm_metadata_references() -> None:
    record = AgentRunRecord(
        agent_run_id="run-1",
        project_id="project-1",
        agent_id="evidence_review",
        agent_version="v1",
        prompt_template_version="prompt-v1",
        llm_metadata_refs=["llm-metadata://project-1/request-1"],
        started_at=datetime.now(UTC),
    )

    assert record.llm_metadata_refs == ["llm-metadata://project-1/request-1"]
    assert "prompt" not in record.model_dump(exclude={"prompt_template_version"})

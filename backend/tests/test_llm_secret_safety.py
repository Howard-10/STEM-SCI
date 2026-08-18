from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel

from stem_sci.agents.runtime import GPTProvider, LLMResponseError, LLMTransportError


class ValueModel(BaseModel):
    value: str


def test_provider_error_does_not_expose_key_or_prompt() -> None:
    secret = "local-api-key-sentinel"
    prompt = "full-prompt-sentinel"

    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=secret)

    provider = GPTProvider(
        base_url="https://gpt.invalid/v1",
        api_key=secret,
        client=httpx.Client(transport=httpx.MockTransport(handle)),
    )

    with pytest.raises(LLMResponseError) as error:
        provider.generate_structured(
            system_prompt=prompt,
            user_prompt=prompt,
            response_model=ValueModel,
            model="gpt-test",
            prompt_version="test-v1",
        )

    assert secret not in str(error.value)
    assert prompt not in str(error.value)


def test_transport_error_is_redacted() -> None:
    secret = "transport-key-sentinel"

    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(secret, request=request)

    provider = GPTProvider(
        base_url="https://gpt.invalid/v1",
        api_key=secret,
        client=httpx.Client(transport=httpx.MockTransport(handle)),
    )

    with pytest.raises(LLMTransportError) as error:
        provider.generate_structured(
            system_prompt="system",
            user_prompt="user",
            response_model=ValueModel,
            model="gpt-test",
            prompt_version="test-v1",
        )

    assert secret not in str(error.value)


def test_env_example_contains_names_but_no_credentials() -> None:
    env_example = Path(__file__).parents[2] / ".env.example"
    text = env_example.read_text(encoding="utf-8")

    assert "STEM_SCI_LLM_PROVIDER=gpt" in text
    assert "STEM_SCI_LLM_MODEL=<set-for-local-deployment>" in text
    assert "STEM_SCI_LLM_API_KEY=" not in text
    assert "local-api-key-sentinel" not in text

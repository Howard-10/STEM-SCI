from __future__ import annotations

import httpx

from stem_sci.agents.runtime.provider import GPTProvider


def test_gpt_provider_parses_function_calls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        payload = request.content.decode("utf-8")
        assert "hybrid_search" in payload
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "hybrid_search",
                                        "arguments": '{"query":"virtual reality"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
            },
        )

    provider = GPTProvider(
        base_url="https://example.test/v1",
        api_key="test-key",
        default_model="test-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = provider.complete(
        messages=[{"role": "user", "content": "search"}],
        model="test-model",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "hybrid_search",
                    "parameters": {"type": "object"},
                },
            }
        ],
    )

    assert result.request_id.startswith("chat-request-")
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "hybrid_search"
    assert result.tool_calls[0].arguments["query"] == "virtual reality"

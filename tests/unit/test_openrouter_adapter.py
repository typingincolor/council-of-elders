"""Unit tests for OpenRouterAdapter using httpx.MockTransport (no network)."""

from __future__ import annotations

import pytest

from council.adapters.elders.openrouter import OpenRouterAdapter, OpenRouterError


class TestConstructorAndHealth:
    def test_exposes_elder_id(self):
        a = OpenRouterAdapter(
            elder_id="claude", model="anthropic/claude-sonnet-4.5", api_key="sk-or-x"
        )
        assert a.elder_id == "claude"

    async def test_health_check_true_when_key_set(self):
        a = OpenRouterAdapter(
            elder_id="claude", model="anthropic/claude-sonnet-4.5", api_key="sk-or-x"
        )
        assert await a.health_check() is True

    async def test_health_check_false_when_key_empty(self):
        a = OpenRouterAdapter(
            elder_id="claude", model="anthropic/claude-sonnet-4.5", api_key=""
        )
        assert await a.health_check() is False

    def test_error_class_has_kind_and_detail(self):
        e = OpenRouterError("auth_failed", "bad key")
        assert e.kind == "auth_failed"
        assert e.detail == "bad key"


import httpx


def _adapter_with_transport(transport: httpx.MockTransport) -> OpenRouterAdapter:
    return OpenRouterAdapter(
        elder_id="claude",
        model="anthropic/claude-sonnet-4.5",
        api_key="sk-or-test",
        client=httpx.AsyncClient(transport=transport, base_url="https://openrouter.ai"),
    )


class TestAskHappyPath:
    async def test_returns_message_content(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "id": "gen-1",
                    "choices": [{"message": {"role": "assistant", "content": "hello"}}],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 2,
                        "total_tokens": 12,
                        "cost": 0.0005,
                    },
                },
            )

        a = _adapter_with_transport(httpx.MockTransport(handler))
        reply = await a.ask("hi")
        assert reply == "hello"

    async def test_sends_expected_request(self):
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(
                200,
                json={
                    "id": "gen-1",
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0},
                },
            )

        a = _adapter_with_transport(httpx.MockTransport(handler))
        await a.ask("hello world")

        import json as _json

        assert len(captured) == 1
        req = captured[0]
        assert req.method == "POST"
        assert str(req.url) == "https://openrouter.ai/api/v1/chat/completions"
        assert req.headers["Authorization"] == "Bearer sk-or-test"
        assert req.headers["Content-Type"].startswith("application/json")
        body = _json.loads(req.content)
        assert body["model"] == "anthropic/claude-sonnet-4.5"
        assert body["messages"] == [{"role": "user", "content": "hello world"}]
        assert body["usage"] == {"include": True}

"""Unit tests for OpenRouterAdapter using httpx.MockTransport (no network)."""

from __future__ import annotations

import httpx
import pytest

from council.adapters.elders.openrouter import (
    OpenRouterAdapter,
    OpenRouterError,
    format_cost_notice,
)


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


class TestAskErrorMapping:
    async def test_401_maps_to_auth_failed(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "invalid key"}})

        a = _adapter_with_transport(httpx.MockTransport(handler))
        with pytest.raises(OpenRouterError) as ei:
            await a.ask("hi")
        assert ei.value.kind == "auth_failed"

    async def test_403_maps_to_auth_failed(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(403, text="forbidden")

        a = _adapter_with_transport(httpx.MockTransport(handler))
        with pytest.raises(OpenRouterError) as ei:
            await a.ask("hi")
        assert ei.value.kind == "auth_failed"

    async def test_429_maps_to_quota_exhausted(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text="slow down")

        a = _adapter_with_transport(httpx.MockTransport(handler))
        with pytest.raises(OpenRouterError) as ei:
            await a.ask("hi")
        assert ei.value.kind == "quota_exhausted"

    async def test_500_maps_to_nonzero_exit(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="server exploded")

        a = _adapter_with_transport(httpx.MockTransport(handler))
        with pytest.raises(OpenRouterError) as ei:
            await a.ask("hi")
        assert ei.value.kind == "nonzero_exit"
        assert "500" in ei.value.detail

    async def test_malformed_json_maps_to_unparseable(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"weird": True})

        a = _adapter_with_transport(httpx.MockTransport(handler))
        with pytest.raises(OpenRouterError) as ei:
            await a.ask("hi")
        assert ei.value.kind == "unparseable"

    async def test_timeout_maps_to_timeout(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("slow")

        a = _adapter_with_transport(httpx.MockTransport(handler))
        with pytest.raises(OpenRouterError) as ei:
            await a.ask("hi", timeout_s=0.1)
        assert ei.value.kind == "timeout"

    async def test_network_error_maps_to_nonzero_exit(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route")

        a = _adapter_with_transport(httpx.MockTransport(handler))
        with pytest.raises(OpenRouterError) as ei:
            await a.ask("hi")
        assert ei.value.kind == "nonzero_exit"


class TestEmptyContentFallback:
    async def test_empty_content_falls_back_to_reasoning(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "id": "g",
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "reasoning": "the real answer",
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0},
                },
            )

        a = _adapter_with_transport(httpx.MockTransport(handler))
        reply = await a.ask("hi")
        assert reply == "the real answer"

    async def test_null_content_falls_back_to_reasoning(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "id": "g",
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "reasoning": "the real answer",
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0},
                },
            )

        a = _adapter_with_transport(httpx.MockTransport(handler))
        reply = await a.ask("hi")
        assert reply == "the real answer"

    async def test_both_empty_raises_unparseable(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "id": "g",
                    "choices": [{"message": {"content": "", "reasoning": ""}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 0, "cost": 0.0},
                },
            )

        a = _adapter_with_transport(httpx.MockTransport(handler))
        with pytest.raises(OpenRouterError) as ei:
            await a.ask("hi")
        assert ei.value.kind == "unparseable"


class TestCostCapture:
    async def test_accumulates_cost_and_tokens_across_calls(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "id": "g",
                    "choices": [{"message": {"content": "reply"}}],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "cost": 0.001,
                    },
                },
            )

        a = _adapter_with_transport(httpx.MockTransport(handler))
        await a.ask("one")
        await a.ask("two")
        assert a.session_cost_usd == pytest.approx(0.002)
        assert a.session_tokens == {"prompt": 20, "completion": 10}

    async def test_missing_cost_leaves_total_unchanged(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "id": "g",
                    "choices": [{"message": {"content": "reply"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                },
            )

        a = _adapter_with_transport(httpx.MockTransport(handler))
        await a.ask("hi")
        assert a.session_cost_usd == 0.0
        assert a.session_tokens == {"prompt": 1, "completion": 1}


class TestFormatCostNotice:
    def test_with_known_limit_shows_remaining(self):
        a = OpenRouterAdapter(
            elder_id="claude", model="x", api_key="k"
        )
        a.session_cost_usd = 0.10
        b = OpenRouterAdapter(
            elder_id="gemini", model="x", api_key="k"
        )
        b.session_cost_usd = 0.05
        line = format_cost_notice(
            elders={"claude": a, "gemini": b},
            round_cost_delta_usd=0.03,
            credits_used=2.5,
            credits_limit=10.0,
        )
        assert "round: $0.0300" in line
        assert "session: $0.1500" in line
        assert "credits remaining: $7.50" in line

    def test_with_no_limit_shows_used(self):
        a = OpenRouterAdapter(
            elder_id="claude", model="x", api_key="k"
        )
        line = format_cost_notice(
            elders={"claude": a},
            round_cost_delta_usd=0.01,
            credits_used=3.25,
            credits_limit=None,
        )
        assert "credits used: $3.25" in line
        assert "remaining" not in line


class TestFetchCredits:
    async def test_returns_used_and_limit(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/v1/credits"
            return httpx.Response(
                200,
                json={"data": {"total_credits": 10.0, "total_usage": 2.5}},
            )

        a = _adapter_with_transport(httpx.MockTransport(handler))
        used, limit = await a.fetch_credits()
        assert used == pytest.approx(2.5)
        assert limit == pytest.approx(10.0)

    async def test_missing_data_returns_safe_default(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={})

        a = _adapter_with_transport(httpx.MockTransport(handler))
        used, limit = await a.fetch_credits()
        assert used == 0.0
        assert limit is None

    async def test_http_error_returns_safe_default(self):
        def handler(_req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route")

        a = _adapter_with_transport(httpx.MockTransport(handler))
        used, limit = await a.fetch_credits()
        assert used == 0.0
        assert limit is None

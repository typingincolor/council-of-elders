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

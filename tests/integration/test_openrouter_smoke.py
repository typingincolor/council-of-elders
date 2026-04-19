"""Hits the real OpenRouter API. Skipped unless OPENROUTER_API_KEY is set."""

from __future__ import annotations

import os

import pytest

from council.adapters.elders.openrouter import OpenRouterAdapter


@pytest.mark.integration
async def test_openrouter_round_trip():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        pytest.skip("OPENROUTER_API_KEY not set")
    adapter = OpenRouterAdapter(
        elder_id="claude",
        model="openai/gpt-4o-mini",  # cheap, widely available
        api_key=key,
    )
    reply = await adapter.ask("Say exactly the word 'hi' and nothing else.", timeout_s=30)
    assert reply.strip()


@pytest.mark.integration
async def test_openrouter_fetch_credits():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        pytest.skip("OPENROUTER_API_KEY not set")
    adapter = OpenRouterAdapter(
        elder_id="claude",
        model="openai/gpt-4o-mini",
        api_key=key,
    )
    used, limit = await adapter.fetch_credits()
    assert used >= 0.0
    assert limit is None or limit >= 0.0

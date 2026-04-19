"""Contract tests every ElderPort implementation must satisfy.

FakeElder always runs. Real-CLI adapters are parameterized with the
`integration` marker, so they only run under `pytest -m integration`
(the default pytest config uses `-m 'not integration'`).
"""

from __future__ import annotations

import httpx
import pytest

from council.adapters.elders.fake import FakeElder
from council.domain.models import Message


def _fake_elder():
    return FakeElder(
        elder_id="claude",
        replies=["The first answer.\nCONVERGED: yes"],
    )


def _openrouter_mocked():
    from council.adapters.elders.openrouter import OpenRouterAdapter

    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "gen-contract",
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0},
            },
        )

    return OpenRouterAdapter(
        elder_id="claude",
        model="anthropic/claude-sonnet-4.5",
        api_key="sk-or-contract",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://openrouter.ai",
        ),
    )


def _claude_real():
    from council.adapters.elders.claude_code import ClaudeCodeAdapter

    return ClaudeCodeAdapter()


def _gemini_real():
    from council.adapters.elders.gemini_cli import GeminiCLIAdapter

    return GeminiCLIAdapter()


def _codex_real():
    from council.adapters.elders.codex_cli import CodexCLIAdapter

    return CodexCLIAdapter()


ELDERS_UNDER_CONTRACT = [
    pytest.param(_fake_elder, id="fake"),
    pytest.param(_openrouter_mocked, id="openrouter-mocked"),
    pytest.param(_claude_real, id="claude-real", marks=pytest.mark.integration),
    pytest.param(_gemini_real, id="gemini-real", marks=pytest.mark.integration),
    pytest.param(_codex_real, id="codex-real", marks=pytest.mark.integration),
]


@pytest.fixture(params=ELDERS_UNDER_CONTRACT)
def elder_factory(request):
    return request.param


class TestElderPortContract:
    async def test_ask_returns_nonempty_string(self, elder_factory):
        elder = elder_factory()
        reply = await elder.ask([Message("user", "Say hello.")], timeout_s=60)
        assert isinstance(reply, str)
        assert reply.strip()

    async def test_health_check_is_bool(self, elder_factory):
        elder = elder_factory()
        result = await elder.health_check()
        assert isinstance(result, bool)

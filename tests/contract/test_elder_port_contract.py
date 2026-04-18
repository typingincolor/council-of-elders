"""Contract tests every ElderPort implementation must satisfy.

FakeElder always runs. Real-CLI adapters are parameterized with the
`integration` marker, so they only run under `pytest -m integration`
(the default pytest config uses `-m 'not integration'`).
"""
from __future__ import annotations

import pytest

from council.adapters.elders.fake import FakeElder


def _fake_elder():
    return FakeElder(
        elder_id="claude",
        replies=["The first answer.\nCONVERGED: yes"],
    )


# Real adapter factories import lazily — they're only imported when selected.
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
        reply = await elder.ask("Say hello.", timeout_s=60)
        assert isinstance(reply, str)
        assert reply.strip()

    async def test_health_check_is_bool(self, elder_factory):
        elder = elder_factory()
        result = await elder.health_check()
        assert isinstance(result, bool)

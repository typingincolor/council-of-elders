from datetime import datetime, timezone
from pathlib import Path
import pytest

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.storage.in_memory import InMemoryStore
from council.app.headless.main import run_headless
from council.domain.models import CouncilPack


async def test_headless_runs_one_round_and_synthesizes(capsys):
    elders = {
        "claude": FakeElder(
            elder_id="claude",
            replies=[
                "R1 Claude\nCONVERGED: yes",
                "Final synthesized answer.",
            ],
        ),
        "gemini": FakeElder(
            elder_id="gemini", replies=["R1 Gemini\nCONVERGED: yes"]
        ),
        "chatgpt": FakeElder(
            elder_id="chatgpt", replies=["R1 ChatGPT\nCONVERGED: yes"]
        ),
    }
    pack = CouncilPack(name="bare", shared_context=None, personas={})
    await run_headless(
        prompt="What should I do?",
        pack=pack,
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 18, tzinfo=timezone.utc)),
        bus=InMemoryBus(),
        synthesizer="claude",
    )
    out = capsys.readouterr().out
    assert "R1 Claude" in out
    assert "R1 Gemini" in out
    assert "R1 ChatGPT" in out
    assert "Final synthesized answer." in out

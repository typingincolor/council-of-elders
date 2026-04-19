import asyncio
from datetime import datetime, timezone

from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.in_memory import InMemoryStore
from council.app.tui.app import CouncilApp
from tests.e2e.conftest import pane_lines


async def _wait_until(pilot, predicate, *, timeout_s=5.0, tick=0.05):
    elapsed = 0.0
    while not predicate():
        await pilot.pause()
        await asyncio.sleep(tick)
        elapsed += tick
        if elapsed > timeout_s:
            raise AssertionError(f"Timed out; elapsed={elapsed:.2f}s")


async def test_two_rounds_appear_in_each_elder_pane_with_divider(tmp_path):
    # R1+R2 auto-chain produces both rounds without user interaction.
    (tmp_path / "bare").mkdir()
    elders = {
        "claude": FakeElder(
            elder_id="claude",
            replies=[
                "R1 Claude text",
                "R2 Claude text\n\nQUESTIONS:\n@gemini Why?",
            ],
        ),
        "gemini": FakeElder(
            elder_id="gemini",
            replies=[
                "R1 Gemini text",
                "R2 Gemini text\n\nQUESTIONS:\n@claude Why?",
            ],
        ),
        "chatgpt": FakeElder(
            elder_id="chatgpt",
            replies=[
                "R1 ChatGPT text",
                "R2 ChatGPT text\n\nQUESTIONS:\n@gemini Why?",
            ],
        ),
    }
    app = CouncilApp(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 19, tzinfo=timezone.utc)),
        pack_loader=FilesystemPackLoader(root=tmp_path),
        pack_name="bare",
    )
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.press(*"Two rounds?")
        await pilot.press("enter")
        # Wait for the auto-chained R1+R2 opening exchange to complete.
        await _wait_until(pilot, lambda: app.awaiting_decision)
        await _wait_until(pilot, lambda: len(app._debate.rounds) >= 2 if app._debate else False)

        for elder, r1_text, r2_text in [
            ("claude", "R1 Claude text", "R2 Claude text"),
            ("gemini", "R1 Gemini text", "R2 Gemini text"),
            ("chatgpt", "R1 ChatGPT text", "R2 ChatGPT text"),
        ]:
            text = pane_lines(app, elder)
            assert r1_text in text
            assert r2_text in text
            assert "Round 2" in text

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


async def test_elder_question_surfaces_in_both_asker_and_target_panes(tmp_path):
    (tmp_path / "bare").mkdir()
    elders = {
        "claude": FakeElder(
            elder_id="claude",
            replies=["My answer.\n\nQUESTIONS:\n@gemini Timeline?\n\nCONVERGED: no"],
        ),
        "gemini": FakeElder(elder_id="gemini", replies=["mine\nCONVERGED: no"]),
        "chatgpt": FakeElder(elder_id="chatgpt", replies=["mine\nCONVERGED: no"]),
    }
    app = CouncilApp(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 19, tzinfo=timezone.utc)),
        pack_loader=FilesystemPackLoader(root=tmp_path),
        pack_name="bare",
    )
    async with app.run_test() as pilot:
        await pilot.press(*"Go")
        await pilot.press("enter")
        await _wait_until(pilot, lambda: app.awaiting_decision)

        # Claude's pane should show the outgoing question.
        claude_text = pane_lines(app, "claude")
        assert "To Gemini" in claude_text
        assert "Timeline?" in claude_text

        # Gemini's pane should show the incoming question.
        gemini_text = pane_lines(app, "gemini")
        assert "From Claude" in gemini_text
        assert "Timeline?" in gemini_text

        # ChatGPT's pane should NOT show this question (not directed at it).
        chatgpt_text = pane_lines(app, "chatgpt")
        assert "Timeline?" not in chatgpt_text

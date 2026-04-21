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
    # Questions first appear in R2 (cross-examination). R1 is silent.
    (tmp_path / "bare").mkdir()
    elders = {
        "ada": FakeElder(
            elder_id="ada",
            replies=[
                "R1 Ada",
                "My answer.\n\nQUESTIONS:\n@kai Timeline?",
            ],
        ),
        "kai": FakeElder(
            elder_id="kai",
            replies=[
                "R1 Kai",
                "Kai R2\n\nQUESTIONS:\n@ada Why?",
            ],
        ),
        "mei": FakeElder(
            elder_id="mei",
            replies=[
                "R1 Mei",
                "Mei R2\n\nQUESTIONS:\n@ada Why?",
            ],
        ),
    }
    app = CouncilApp(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 19, tzinfo=timezone.utc)),
        pack_loader=FilesystemPackLoader(root=tmp_path),
        pack_name="bare",
        mode="full",
    )
    async with app.run_test() as pilot:
        await pilot.press(*"Go")
        await pilot.press("enter")
        # awaiting_decision flips True only after R2 completes (post-auto-chain).
        await _wait_until(pilot, lambda: app.awaiting_decision)

        # Ada's pane should show the outgoing question (emitted in R2).
        claude_text = pane_lines(app, "ada")
        assert "To Kai" in claude_text
        assert "Timeline?" in claude_text

        # Kai's pane should show the incoming question.
        gemini_text = pane_lines(app, "kai")
        assert "From Ada" in gemini_text
        assert "Timeline?" in gemini_text

        # Mei's pane should NOT show the claude→gemini question.
        chatgpt_text = pane_lines(app, "mei")
        assert "Timeline?" not in chatgpt_text

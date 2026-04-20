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


async def test_user_message_appears_in_all_elder_panes(tmp_path):
    (tmp_path / "bare").mkdir()
    # R1+R2 auto-chain runs before awaiting_decision flips to True.
    elders = {
        "ada": FakeElder(
            elder_id="ada",
            replies=["R1 c", "R2 c\n\nQUESTIONS:\n@kai Why?"],
        ),
        "kai": FakeElder(
            elder_id="kai",
            replies=["R1 g", "R2 g\n\nQUESTIONS:\n@ada Why?"],
        ),
        "mei": FakeElder(
            elder_id="mei",
            replies=["R1 x", "R2 x\n\nQUESTIONS:\n@kai Why?"],
        ),
    }
    app = CouncilApp(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 19, tzinfo=timezone.utc)),
        pack_loader=FilesystemPackLoader(root=tmp_path),
        pack_name="bare",
    )
    async with app.run_test() as pilot:
        await pilot.press(*"Initial question")
        await pilot.press("enter")
        await _wait_until(pilot, lambda: app.awaiting_decision)

        # Type a user message and submit.
        # Input is re-enabled at awaiting_decision; focus it first.
        app.query_one("#input").focus()
        await pilot.press(*"please focus on timeline")
        await pilot.press("enter")
        await pilot.pause()

        for elder in ("ada", "kai", "mei"):
            text = pane_lines(app, elder)
            assert "please focus on timeline" in text
            # after_round reflects the most recent completed round (R2 here).
            assert "You after round 2" in text

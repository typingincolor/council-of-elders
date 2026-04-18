import asyncio
from datetime import datetime, timezone

from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.storage.in_memory import InMemoryStore
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.app.tui.app import CouncilApp


async def _wait_until(pilot, predicate, *, timeout_s=5.0, tick=0.05):
    elapsed = 0.0
    while not predicate():
        await pilot.pause()
        await asyncio.sleep(tick)
        elapsed += tick
        if elapsed > timeout_s:
            raise AssertionError(f"Timed out waiting for predicate; elapsed={elapsed:.2f}s")


async def test_full_debate_via_tui(tmp_path):
    # Pack with only shared context
    (tmp_path / "bare").mkdir()
    loader = FilesystemPackLoader(root=tmp_path)

    elders = {
        "claude": FakeElder(
            elder_id="claude",
            replies=[
                "R1 Claude\nCONVERGED: yes",
                "Final synthesized answer.",
            ],
        ),
        "gemini": FakeElder(elder_id="gemini", replies=["R1 Gemini\nCONVERGED: yes"]),
        "chatgpt": FakeElder(elder_id="chatgpt", replies=["R1 ChatGPT\nCONVERGED: yes"]),
    }
    app = CouncilApp(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 18, tzinfo=timezone.utc)),
        pack_loader=loader,
        pack_name="bare",
    )

    async with app.run_test() as pilot:
        await pilot.press(*"What should I do?")
        await pilot.press("enter")
        await _wait_until(pilot, lambda: app.awaiting_decision)
        assert app.awaiting_decision is True

        await pilot.press("s")
        # Wait for modal to be pushed onto the screen stack before pressing '1'
        await _wait_until(pilot, lambda: len(app.screen_stack) > 1, timeout_s=2.0)
        await pilot.press("1")  # 1 => Claude
        await _wait_until(pilot, lambda: app.is_finished)
        assert app.is_finished is True

    # Stream should contain all three elder answers and the synthesis
    transcript = "\n".join(app.rendered_lines)
    assert "R1 Claude" in transcript
    assert "R1 Gemini" in transcript
    assert "R1 ChatGPT" in transcript
    assert "Final synthesized answer." in transcript

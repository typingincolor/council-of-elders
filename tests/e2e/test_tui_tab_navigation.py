import asyncio
from datetime import datetime, timezone

from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.in_memory import InMemoryStore
from council.app.tui.app import CouncilApp


def _app(tmp_path):
    (tmp_path / "bare").mkdir()
    elders = {
        "claude": FakeElder(elder_id="claude", replies=["r1\nCONVERGED: yes"]),
        "gemini": FakeElder(elder_id="gemini", replies=["r1\nCONVERGED: yes"]),
        "chatgpt": FakeElder(elder_id="chatgpt", replies=["r1\nCONVERGED: yes"]),
    }
    return CouncilApp(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 19, tzinfo=timezone.utc)),
        pack_loader=FilesystemPackLoader(root=tmp_path),
        pack_name="bare",
    )


async def _wait_until(pilot, predicate, *, timeout_s=5.0, tick=0.05):
    elapsed = 0.0
    while not predicate():
        await pilot.pause()
        await asyncio.sleep(tick)
        elapsed += tick
        if elapsed > timeout_s:
            raise AssertionError(f"Timed out; elapsed={elapsed:.2f}s")


async def test_number_key_focuses_correct_pane(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(80, 40)) as pilot:  # narrow → tabs
        await pilot.press(*"Any question")
        await pilot.press("ctrl+enter")
        await _wait_until(pilot, lambda: app.awaiting_decision)

        for key, elder in [("2", "gemini"), ("3", "chatgpt"), ("4", "synthesis"), ("1", "claude")]:
            await pilot.press(key)
            await pilot.pause()
            assert app._view.pane(elder).has_focus

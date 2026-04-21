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
        "ada": FakeElder(elder_id="ada", replies=["r1\nCONVERGED: yes"]),
        "kai": FakeElder(elder_id="kai", replies=["r1\nCONVERGED: yes"]),
        "mei": FakeElder(elder_id="mei", replies=["r1\nCONVERGED: yes"]),
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
        await pilot.press("enter")
        await _wait_until(pilot, lambda: app.awaiting_decision)

        # 1/2/3 work any time — elder tabs are always present.
        # 4 (synthesis) only works once synthesis is revealed; test it
        # separately by showing the pane first.
        for key, elder in [("2", "kai"), ("3", "mei"), ("1", "ada")]:
            await pilot.press(key)
            await pilot.pause()
            assert app._view.pane(elder).has_focus

        await app._view.show_synthesis_pane()
        await pilot.pause()
        await pilot.press("4")
        await pilot.pause()
        assert app._view.pane("synthesis").has_focus

"""The TUI should probe each elder at startup and surface unhealthy ones in
the stream. If all three are unhealthy, the input is disabled so the user
can't waste a prompt typing into a dead council."""

import asyncio
from datetime import datetime, timezone

from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.in_memory import InMemoryStore
from council.app.tui.app import CouncilApp


async def _wait_until(pilot, predicate, *, timeout_s=5.0, tick=0.05):
    elapsed = 0.0
    while not predicate():
        await pilot.pause()
        await asyncio.sleep(tick)
        elapsed += tick
        if elapsed > timeout_s:
            raise AssertionError(f"Timed out; elapsed={elapsed:.2f}s")


def _app(tmp_path, elders):
    (tmp_path / "bare").mkdir()
    return CouncilApp(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 19, tzinfo=timezone.utc)),
        pack_loader=FilesystemPackLoader(root=tmp_path),
        pack_name="bare",
    )


async def test_no_warning_when_all_elders_healthy(tmp_path):
    app = _app(
        tmp_path,
        elders={
            "claude": FakeElder(elder_id="claude", replies=[], healthy=True),
            "gemini": FakeElder(elder_id="gemini", replies=[], healthy=True),
            "chatgpt": FakeElder(elder_id="chatgpt", replies=[], healthy=True),
        },
    )
    async with app.run_test() as pilot:
        # Give the health-check task a chance to run.
        for _ in range(5):
            await pilot.pause()
        transcript = "\n".join(app.rendered_lines)
        assert "unavailable" not in transcript
        assert "No elders available" not in transcript


async def test_unhealthy_elder_produces_warning_line(tmp_path):
    app = _app(
        tmp_path,
        elders={
            "claude": FakeElder(elder_id="claude", replies=[], healthy=True),
            "gemini": FakeElder(elder_id="gemini", replies=[], healthy=False),
            "chatgpt": FakeElder(elder_id="chatgpt", replies=[], healthy=True),
        },
    )
    async with app.run_test() as pilot:
        await _wait_until(
            pilot,
            lambda: any("Gemini CLI is unavailable" in line for line in app.rendered_lines),
        )


async def test_all_unhealthy_disables_input(tmp_path):
    from council.app.tui.app import CouncilInput

    app = _app(
        tmp_path,
        elders={
            "claude": FakeElder(elder_id="claude", replies=[], healthy=False),
            "gemini": FakeElder(elder_id="gemini", replies=[], healthy=False),
            "chatgpt": FakeElder(elder_id="chatgpt", replies=[], healthy=False),
        },
    )
    async with app.run_test() as pilot:
        await _wait_until(
            pilot,
            lambda: app.query_one("#input", CouncilInput).disabled,
        )
        transcript = "\n".join(app.rendered_lines)
        assert "No elders available" in transcript

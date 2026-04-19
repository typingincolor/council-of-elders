from datetime import datetime, timezone

from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.in_memory import InMemoryStore
from council.app.tui.app import CouncilApp


def _app(tmp_path):
    (tmp_path / "bare").mkdir()
    elders = {
        "claude": FakeElder(elder_id="claude", replies=[]),
        "gemini": FakeElder(elder_id="gemini", replies=[]),
        "chatgpt": FakeElder(elder_id="chatgpt", replies=[]),
    }
    return CouncilApp(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 19, tzinfo=timezone.utc)),
        pack_loader=FilesystemPackLoader(root=tmp_path),
        pack_name="bare",
    )


async def test_layout_switches_with_width(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        assert app._view.current_layout() == "tabs"

        await pilot.resize_terminal(300, 40)
        await pilot.pause()
        assert app._view.current_layout() == "columns"


async def test_f_cycles_forced_modes(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        assert app._view.current_layout() == "tabs"

        # Focus on a pane so key presses reach the app
        app._view.pane("claude").focus()
        await pilot.pause()

        await pilot.press("f")  # None -> "tabs"
        await pilot.pause()
        await pilot.press("f")  # "tabs" -> "columns"
        await pilot.pause()
        assert app._view.current_layout() == "columns"

        # Narrow resize should not escape the override.
        await pilot.resize_terminal(80, 40)
        await pilot.pause()
        assert app._view.current_layout() == "columns"

        await pilot.press("f")  # "columns" -> None
        await pilot.pause()
        assert app._view.current_layout() == "tabs"

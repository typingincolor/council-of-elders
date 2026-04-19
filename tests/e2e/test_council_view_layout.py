from datetime import datetime, timezone

from textual.app import App, ComposeResult

from council.adapters.clock.fake import FakeClock
from council.app.tui.council_view import CouncilView
from council.app.tui.verbs import FixedVerbChooser


class _Host(App):
    def __init__(self, view):
        super().__init__()
        self._view = view

    def compose(self) -> ComposeResult:
        yield self._view


def _make_view() -> CouncilView:
    clock = FakeClock(now=datetime(2026, 4, 19, 12, tzinfo=timezone.utc))
    return CouncilView(
        verb_chooser=FixedVerbChooser("Pondering"),
        clock=clock,
    )


async def test_view_has_four_panes_one_per_elder_plus_synthesis():
    view = _make_view()
    async with _Host(view).run_test() as pilot:
        await pilot.pause()
        assert set(view.pane_ids()) == {"claude", "gemini", "chatgpt", "synthesis"}


async def test_narrow_width_selects_tabs_mode():
    view = _make_view()
    async with _Host(view).run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        assert view.current_layout() == "tabs"


async def test_wide_width_selects_columns_mode():
    view = _make_view()
    async with _Host(view).run_test(size=(300, 40)) as pilot:
        await pilot.pause()
        assert view.current_layout() == "columns"


async def test_force_override_sticks_through_resize():
    view = _make_view()
    async with _Host(view).run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        assert view.current_layout() == "tabs"
        view.toggle_forced_mode()  # None -> "tabs"
        view.toggle_forced_mode()  # "tabs" -> "columns"
        await pilot.pause()
        assert view.current_layout() == "columns"
        # Resize to narrow — forced columns should stick.
        await pilot.resize_terminal(80, 40)
        await pilot.pause()
        assert view.current_layout() == "columns"
        # Clear override (back to auto).
        view.toggle_forced_mode()  # "columns" -> None
        await pilot.pause()
        assert view.current_layout() == "tabs"

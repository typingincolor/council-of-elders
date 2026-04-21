"""Composite widget: holds the elder panes plus two optional extras
(Analysis, Synthesis) that only appear after the user triggers them.

Switches between three-column and tabbed layouts based on terminal width.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import TabbedContent, TabPane

from council.adapters.clock.system import SystemClock
from council.app.tui.elder_pane import ElderPaneWidget
from council.app.tui.layout import LayoutMode, pick_layout
from council.app.tui.verbs import RandomVerbChooser, VerbChooser
from council.domain.ports import Clock

_ELDER_CONFIG: tuple[tuple[str, str], ...] = (
    ("ada", "Ada"),
    ("kai", "Kai"),
    ("mei", "Mei"),
)


class CouncilView(Widget):
    """Owns the four ElderPaneWidgets and their layout container."""

    DEFAULT_CSS = """
    CouncilView { height: 1fr; }
    CouncilView > Horizontal > ElderPaneWidget { width: 1fr; }
    CouncilView TabbedContent { height: 1fr; }
    """

    def __init__(
        self,
        *,
        verb_chooser: VerbChooser | None = None,
        clock: Clock | None = None,
    ) -> None:
        super().__init__()
        self._verb_chooser = verb_chooser or RandomVerbChooser()
        self._clock = clock or SystemClock()
        self._forced_mode: LayoutMode | None = None
        self._panes: dict[str, ElderPaneWidget] = self._make_panes()
        self._current_layout: LayoutMode | None = None

    def _make_panes(self) -> dict[str, ElderPaneWidget]:
        panes: dict[str, ElderPaneWidget] = {}
        for elder_id, display in _ELDER_CONFIG:
            panes[elder_id] = ElderPaneWidget(
                elder_id=elder_id,
                display_name=display,
                verb_chooser=self._verb_chooser,
                clock=self._clock,
            )
        # Both extras start hidden. They're revealed by the user pressing
        # `d` (analysis) or `s` (synthesis). We keep them in `_panes` from
        # the start so pane(key) is always safe to call; visibility is a
        # separate concern.
        panes["analysis"] = ElderPaneWidget(
            elder_id="ada",  # identifier unused for special panes
            display_name="Analysis",
            verb_chooser=self._verb_chooser,
            clock=self._clock,
            synthesis=True,
        )
        panes["synthesis"] = ElderPaneWidget(
            elder_id="ada",
            display_name="Synthesis",
            verb_chooser=self._verb_chooser,
            clock=self._clock,
            synthesis=True,
        )
        return panes

    # --- public API ------------------------------------------------------
    def pane_ids(self) -> list[str]:
        return list(self._panes.keys())

    def pane(self, key: str) -> ElderPaneWidget:
        return self._panes[key]

    async def show_analysis_pane(self) -> None:
        """Reveal the analysis pane. Idempotent."""
        await self._show_extra_pane("analysis")

    async def show_synthesis_pane(self) -> None:
        """Reveal the synthesis pane. Idempotent."""
        await self._show_extra_pane("synthesis")

    async def _show_extra_pane(self, key: str) -> None:
        pane = self._panes[key]
        if self._current_layout == "tabs":
            # In tabs mode, extras are added to the TabbedContent the first
            # time they're needed — not at mount — so the tab bar doesn't
            # show empty "Analysis" / "Synthesis" tabs before they have
            # anything in them. add_pane is async; must be awaited to
            # ensure the pane is mounted before the caller renders into it.
            try:
                tabbed = self.query_one(TabbedContent)
            except Exception:
                return
            tab_id = f"pane-{key}"
            if any(getattr(tp, "id", None) == tab_id for tp in tabbed.query(TabPane)):
                return
            await tabbed.add_pane(
                TabPane(pane.display_name, pane, id=tab_id),
            )
        else:
            pane.display = True

    def current_layout(self) -> LayoutMode:
        return self._current_layout or pick_layout(
            self.size.width if self.size else 0, self._forced_mode
        )

    def toggle_forced_mode(self) -> None:
        # Cycle: None -> "tabs" -> "columns" -> None
        if self._forced_mode is None:
            self._forced_mode = "tabs"
        elif self._forced_mode == "tabs":
            self._forced_mode = "columns"
        else:
            self._forced_mode = None
        self._rebuild_if_needed()

    # --- lifecycle -------------------------------------------------------
    def compose(self) -> ComposeResult:
        mode = pick_layout(self.size.width if self.size else 0, self._forced_mode)
        self._current_layout = mode
        yield from self._compose_mode(mode)

    def _compose_mode(self, mode: LayoutMode) -> ComposeResult:
        if mode == "columns":
            yield Horizontal(
                self._panes["ada"],
                self._panes["kai"],
                self._panes["mei"],
                id="columns-container",
            )
            # Analysis and Synthesis both mount below the elder row but
            # start hidden. show_analysis_pane / show_synthesis_pane flips
            # display=True on first use.
            yield self._panes["analysis"]
            yield self._panes["synthesis"]
            self._panes["analysis"].display = False
            self._panes["synthesis"].display = False
        else:
            tabbed = TabbedContent(id="tabs-container")
            yield tabbed

    async def on_mount(self) -> None:
        # Only the three elder tabs are added at mount. Extras (analysis,
        # synthesis) are added dynamically when the user triggers them —
        # so empty tabs don't clutter the bar.
        mode = self._current_layout
        if mode == "tabs":
            tabbed = self.query_one(TabbedContent)
            for key in ("ada", "kai", "mei"):
                await tabbed.add_pane(
                    TabPane(
                        self._panes[key].display_name,
                        self._panes[key],
                        id=f"pane-{key}",
                    )
                )

    def on_resize(self) -> None:
        self._rebuild_if_needed()

    # --- helpers ---------------------------------------------------------
    def _rebuild_if_needed(self) -> None:
        desired = pick_layout(self.size.width if self.size else 0, self._forced_mode)
        if desired == self._current_layout:
            return
        # Re-parent by refreshing: remove current children and recompose.
        self._current_layout = desired
        self.refresh(recompose=True)

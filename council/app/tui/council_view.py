"""Composite widget: holds the four ElderPaneWidgets and switches between
three-column and tabbed layouts based on terminal width."""
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
    ("claude", "Claude"),
    ("gemini", "Gemini"),
    ("chatgpt", "ChatGPT"),
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
        panes["synthesis"] = ElderPaneWidget(
            elder_id="claude",  # identifier is unused for synthesis rendering
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
            # Horizontal with three elder panes; synthesis overlays on completion.
            # For this plan, synthesis pane is ALSO mounted in columns mode so
            # the user can see it filling during synthesis. CSS hides it when
            # idle.
            yield Horizontal(
                self._panes["claude"],
                self._panes["gemini"],
                self._panes["chatgpt"],
                id="columns-container",
            )
            yield self._panes["synthesis"]  # rendered separately; can be hidden via CSS
        else:
            tabbed = TabbedContent(id="tabs-container")
            yield tabbed

    async def on_mount(self) -> None:
        # If we composed tabs mode, populate the TabbedContent now that it's
        # mounted. If we composed columns, nothing more to do.
        mode = self._current_layout
        if mode == "tabs":
            tabbed = self.query_one(TabbedContent)
            for key in ("claude", "gemini", "chatgpt", "synthesis"):
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
        desired = pick_layout(
            self.size.width if self.size else 0, self._forced_mode
        )
        if desired == self._current_layout:
            return
        # Re-parent by refreshing: remove current children and recompose.
        self._current_layout = desired
        self.refresh(recompose=True)

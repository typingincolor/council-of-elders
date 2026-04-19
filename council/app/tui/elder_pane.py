"""Per-elder pane widget.

Owns: one elder's round history + the current thinking state (verb + elapsed
counter). Exposes a `standalone()` classmethod that constructs an instance
without Textual's mount machinery — used by unit tests that only care about
label generation.

`ElderPane` is the logic-only base class; `ElderPaneWidget` is the Textual
Widget subclass that adds compose, reactive label updates, history rendering,
and a 1-second ticker that keeps the elapsed-seconds counter live during a
thinking turn.
"""

from __future__ import annotations

from datetime import datetime

from council.domain.models import ElderAnswer, ElderError
from council.domain.ports import Clock
from council.app.tui.verbs import VerbChooser

_STATE_IDLE = "idle"
_STATE_THINKING = "thinking"
_STATE_CONVERGED = "converged"
_STATE_DISSENTING = "dissenting"
_STATE_ERROR = "error"


class ElderPane:
    """Logic-only base. Task 4 extends this into a Textual Widget."""

    def __init__(
        self,
        *,
        elder_id: str,
        display_name: str,
        verb_chooser: VerbChooser,
        clock: Clock,
        synthesis: bool = False,
    ) -> None:
        self._elder_id = elder_id
        self._display_name = display_name
        self._verb_chooser = verb_chooser
        self._clock = clock
        self._synthesis = synthesis

        self._state = _STATE_IDLE
        self._current_verb: str | None = None
        self._current_round: int | None = None
        self._started_at: datetime | None = None

    # --- factory for unit tests -----------------------------------------
    @classmethod
    def standalone(
        cls,
        *,
        elder_id: str,
        display_name: str,
        verb_chooser: VerbChooser,
        clock: Clock,
        synthesis: bool = False,
    ) -> "ElderPane":
        return cls(
            elder_id=elder_id,
            display_name=display_name,
            verb_chooser=verb_chooser,
            clock=clock,
            synthesis=synthesis,
        )

    # --- state transitions ----------------------------------------------
    def begin_thinking(self, round_number: int) -> None:
        self._current_verb = self._verb_chooser()
        self._current_round = round_number
        self._started_at = self._clock.now()
        self._state = _STATE_THINKING

    def end_thinking_completed(self, answer: ElderAnswer) -> None:
        self._current_verb = None
        self._started_at = None
        if self._synthesis:
            self._state = _STATE_CONVERGED  # any synthesis completion = ✓
        elif answer.agreed is True:
            self._state = _STATE_CONVERGED
        else:
            # False OR None both render as dissent in the label.
            self._state = _STATE_DISSENTING

    def end_thinking_failed(self, error: ElderError) -> None:
        self._current_verb = None
        self._started_at = None
        self._state = _STATE_ERROR

    # --- elapsed seconds ------------------------------------------------
    def _elapsed_seconds(self) -> int:
        if self._started_at is None:
            return 0
        delta = self._clock.now() - self._started_at
        return int(delta.total_seconds())

    # --- label rendering -------------------------------------------------
    def current_label(self) -> str:
        if self._state == _STATE_THINKING:
            elapsed = self._elapsed_seconds()
            if self._synthesis:
                return f"Synthesising… {elapsed}s"
            return f"{self._display_name} · {self._current_verb}… {elapsed}s"
        if self._state == _STATE_CONVERGED:
            return f"{self._display_name} ✓"
        if self._state == _STATE_DISSENTING:
            return f"{self._display_name} ↻"
        if self._state == _STATE_ERROR:
            return f"{self._display_name} ⚠"
        return self._display_name

    def refresh_label(self) -> None:
        """Called by the ticker to force the elapsed-seconds update.

        No-op in the logic-only base; the Widget subclass added in Task 4
        overrides this to push the new label to Textual.
        """
        # Intentionally empty — the label is computed on demand by
        # current_label(); refresh_label() exists for future hook points.
        return


# -------------------------------------------------------------------------
# Textual widget
# -------------------------------------------------------------------------
import asyncio  # noqa: E402

from textual.app import ComposeResult  # noqa: E402
from textual.reactive import reactive  # noqa: E402
from textual.widget import Widget  # noqa: E402
from textual.widgets import RichLog, Static  # noqa: E402

from council.adapters.clock.system import SystemClock  # noqa: E402
from council.app.tui.stream import format_event  # noqa: E402
from council.app.tui.verbs import RandomVerbChooser  # noqa: E402
from council.domain.events import TurnCompleted, TurnFailed  # noqa: E402

_SYNTHESIS_PLACEHOLDER = "[dim]Synthesis runs after you press [bold]s[/] and pick an elder.[/dim]"


class ElderPaneWidget(ElderPane, Widget):
    """Textual widget wrapping the label state machine with a history log."""

    can_focus = True

    DEFAULT_CSS = """
    ElderPaneWidget {
        layout: vertical;
        height: 1fr;
        border: tall $panel;
        padding: 0 1;
    }
    ElderPaneWidget #pane-thinking {
        height: 1;
        color: $text-muted;
    }
    ElderPaneWidget #pane-history {
        height: 1fr;
    }
    """

    label_text: reactive[str] = reactive("")

    def __init__(
        self,
        *,
        elder_id: str,
        display_name: str,
        verb_chooser: VerbChooser | None = None,
        clock: Clock | None = None,
        synthesis: bool = False,
    ) -> None:
        ElderPane.__init__(
            self,
            elder_id=elder_id,
            display_name=display_name,
            verb_chooser=verb_chooser or RandomVerbChooser(),
            clock=clock or SystemClock(),
            synthesis=synthesis,
        )
        Widget.__init__(self)
        self.display_name = display_name  # public for CouncilView / TabbedContent
        self._last_round_rendered: int | None = None
        self.label_text = display_name
        self._history_buffer: list[
            str
        ] = []  # test-observable; immune to RichLog deferred rendering
        self._ticker_task: asyncio.Task | None = None

    def compose(self) -> ComposeResult:
        yield Static("", id="pane-thinking")
        yield RichLog(id="pane-history", markup=True, wrap=True, highlight=False)

    def on_mount(self) -> None:
        if self._synthesis:
            log = self.query_one("#pane-history", RichLog)
            log.write(_SYNTHESIS_PLACEHOLDER)
            self._history_buffer.append(_SYNTHESIS_PLACEHOLDER)

    # --- state transitions override: sync UI -----------------------------
    def begin_thinking(self, round_number: int) -> None:
        super().begin_thinking(round_number)
        self.label_text = self.current_label()
        self._render_thinking_line()
        self._cancel_ticker()
        self._ticker_task = asyncio.create_task(self._tick_loop())

    def end_thinking_completed(self, answer: ElderAnswer) -> None:
        self._cancel_ticker()
        super().end_thinking_completed(answer)
        self._clear_thinking_line()
        self._append_completed(answer)
        self.label_text = self.current_label()

    def end_thinking_failed(self, error: ElderError) -> None:
        self._cancel_ticker()
        super().end_thinking_failed(error)
        self._clear_thinking_line()
        self._append_failed(error)
        self.label_text = self.current_label()

    def refresh_label(self) -> None:
        self.label_text = self.current_label()
        self._render_thinking_line()

    def _cancel_ticker(self) -> None:
        if self._ticker_task is not None:
            self._ticker_task.cancel()
            self._ticker_task = None

    async def _tick_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(1)
                self.refresh_label()
        except asyncio.CancelledError:
            return

    async def on_unmount(self) -> None:
        self._cancel_ticker()

    # --- internals -------------------------------------------------------
    def _render_thinking_line(self) -> None:
        thinking = self.query_one("#pane-thinking", Static)
        thinking.update(f"[dim]{self.current_label()}[/dim]")

    def _clear_thinking_line(self) -> None:
        self.query_one("#pane-thinking", Static).update("")

    def _append_completed(self, answer: ElderAnswer) -> None:
        log = self.query_one("#pane-history", RichLog)
        if self._synthesis:
            log.clear()  # replace placeholder or previous synthesis
            self._history_buffer.clear()
        else:
            if (
                self._current_round
                and self._current_round >= 2
                and (self._last_round_rendered != self._current_round)
            ):
                divider = f"[dim]─── Round {self._current_round} ───[/dim]"
                log.write(divider)
                self._history_buffer.append(divider)
        line = format_event(
            TurnCompleted(
                elder=answer.elder,
                round_number=self._current_round or 1,
                answer=answer,
            )
        )
        log.write(line)
        self._history_buffer.append(line)
        self._last_round_rendered = self._current_round

    def _append_failed(self, error: ElderError) -> None:
        log = self.query_one("#pane-history", RichLog)
        if not self._synthesis:
            if (
                self._current_round
                and self._current_round >= 2
                and (self._last_round_rendered != self._current_round)
            ):
                divider = f"[dim]─── Round {self._current_round} ───[/dim]"
                log.write(divider)
                self._history_buffer.append(divider)
        line = format_event(
            TurnFailed(
                elder=error.elder,
                round_number=self._current_round or 1,
                error=error,
            )
        )
        log.write(line)
        self._history_buffer.append(line)
        self._last_round_rendered = self._current_round

    # --- test helper -----------------------------------------------------
    def history_text(self) -> str:
        """Return all written history as a single string.

        Uses an internal buffer rather than RichLog.lines so that it works
        for inactive tabs (where RichLog defers rendering until size is known).
        """
        return "\n".join(self._history_buffer)

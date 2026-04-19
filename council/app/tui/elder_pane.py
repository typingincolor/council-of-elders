"""Per-elder pane widget.

Owns: one elder's round history + the current thinking state (verb + elapsed
counter). Exposes a `standalone()` classmethod that constructs an instance
without Textual's mount machinery — used by unit tests that only care about
label generation.

This module currently only implements label-generation logic. Full widget
rendering (history, mount, compose, reactive updates) is added in Task 4.
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

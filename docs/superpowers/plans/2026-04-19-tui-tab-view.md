# TUI Tab View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single chronological-stream TUI with a per-elder pane layout (plus a synthesis pane) that switches responsively between three side-by-side columns (terminals ≥ 240 cols) and tabbed mode (narrower).

**Architecture:** Primary-adapter change only — all new code lives under `council/app/tui/`. Domain core, ports, adapters, event model, and `DebateService` do not change. Two new widgets (`ElderPane`, `CouncilView`), a small layout helper module, and a verb module. `CouncilApp` is rewritten as plumbing.

**Tech Stack:** Python 3.12+, Textual (widgets + `run_test` pilot), pytest + pytest-asyncio, ruff.

**Reference spec:** `docs/superpowers/specs/2026-04-19-tui-tab-view-design.md`

---

## Task 1: Verb chooser and pool

**Files:**
- Create: `council/app/tui/verbs.py`
- Test: `tests/unit/test_verb_chooser.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_verb_chooser.py`:

```python
from unittest.mock import patch

from council.app.tui.verbs import (
    FixedVerbChooser,
    RandomVerbChooser,
    VERB_POOL,
)


class TestVerbPool:
    def test_pool_contains_expected_verbs(self):
        assert "Pondering" in VERB_POOL
        assert "Deliberating" in VERB_POOL
        assert "Cogitating" in VERB_POOL
        assert len(VERB_POOL) == 12

    def test_pool_is_tuple_not_list(self):
        # immutable to prevent accidental mutation at runtime
        assert isinstance(VERB_POOL, tuple)


class TestFixedVerbChooser:
    def test_always_returns_the_fixed_verb(self):
        c = FixedVerbChooser("Pondering")
        assert c() == "Pondering"
        assert c() == "Pondering"


class TestRandomVerbChooser:
    def test_returns_a_verb_from_the_pool(self):
        c = RandomVerbChooser()
        # patch random.choice so we don't need to sample many times
        with patch("council.app.tui.verbs.random.choice", return_value="Noodling"):
            assert c() == "Noodling"

    def test_multiple_calls_all_return_pool_members(self):
        c = RandomVerbChooser()
        for _ in range(20):
            assert c() in VERB_POOL
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_verb_chooser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'council.app.tui.verbs'`

- [ ] **Step 3: Implement `council/app/tui/verbs.py`**

```python
"""Thinking-state verbs for the TUI.

When an elder (or the synthesiser) is mid-turn, its pane label cycles through
a rotating whimsical verb plus an elapsed-seconds counter. Elder-themed
vocabulary fits the "council of elders" metaphor.
"""
from __future__ import annotations

import random
from typing import Protocol

VERB_POOL: tuple[str, ...] = (
    "Pondering",
    "Deliberating",
    "Ruminating",
    "Mulling",
    "Reflecting",
    "Brewing",
    "Cogitating",
    "Meditating",
    "Musing",
    "Noodling",
    "Pontificating",
    "Contemplating",
)


class VerbChooser(Protocol):
    """Callable that returns a thinking verb to display."""

    def __call__(self) -> str: ...


class RandomVerbChooser:
    """Default chooser — picks uniformly from VERB_POOL per call."""

    def __call__(self) -> str:
        return random.choice(VERB_POOL)


class FixedVerbChooser:
    """Deterministic chooser for tests."""

    def __init__(self, verb: str) -> None:
        self._verb = verb

    def __call__(self) -> str:
        return self._verb
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_verb_chooser.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add council/app/tui/verbs.py tests/unit/test_verb_chooser.py
git commit -m "feat(tui): add verb pool and VerbChooser protocol"
```

---

## Task 2: Layout threshold helper

**Files:**
- Create: `council/app/tui/layout.py`
- Test: `tests/unit/test_layout_threshold.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_layout_threshold.py`:

```python
import pytest

from council.app.tui.layout import (
    MIN_WIDTH_3COL,
    MIN_WIDTH_PER_ELDER,
    pick_layout,
)


def test_constants_match_spec():
    # Spec: at least 80 readable columns per elder × 3 elders = 240 total.
    assert MIN_WIDTH_PER_ELDER == 80
    assert MIN_WIDTH_3COL == 240


class TestPickLayoutAuto:
    def test_well_above_threshold_returns_columns(self):
        assert pick_layout(400, forced=None) == "columns"

    def test_exactly_at_threshold_returns_columns(self):
        assert pick_layout(240, forced=None) == "columns"

    def test_one_below_threshold_returns_tabs(self):
        assert pick_layout(239, forced=None) == "tabs"

    def test_narrow_terminal_returns_tabs(self):
        assert pick_layout(80, forced=None) == "tabs"


class TestPickLayoutForced:
    @pytest.mark.parametrize("width", [0, 80, 239, 240, 1000])
    def test_forced_tabs_overrides_width(self, width):
        assert pick_layout(width, forced="tabs") == "tabs"

    @pytest.mark.parametrize("width", [0, 80, 239, 240, 1000])
    def test_forced_columns_overrides_width(self, width):
        assert pick_layout(width, forced="columns") == "columns"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_layout_threshold.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'council.app.tui.layout'`

- [ ] **Step 3: Implement `council/app/tui/layout.py`**

```python
"""Responsive layout mode selection for the council TUI.

Three-column mode is used when the terminal is wide enough to give each elder
at least 80 readable characters. Below that, tabs.
"""
from __future__ import annotations

from typing import Literal

LayoutMode = Literal["tabs", "columns"]

MIN_WIDTH_PER_ELDER: int = 80
MIN_WIDTH_3COL: int = 3 * MIN_WIDTH_PER_ELDER  # 240


def pick_layout(width: int, forced: LayoutMode | None) -> LayoutMode:
    """Decide whether to render tabs or three columns.

    If `forced` is set (by the user toggling `f`), that choice wins.
    Otherwise we pick based on the terminal width.
    """
    if forced is not None:
        return forced
    return "columns" if width >= MIN_WIDTH_3COL else "tabs"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_layout_threshold.py -v`
Expected: 14 passed (1 + 4 + 5 + 5 after parametrize expansion).

- [ ] **Step 5: Commit**

```bash
git add council/app/tui/layout.py tests/unit/test_layout_threshold.py
git commit -m "feat(tui): add responsive layout threshold helper"
```

---

## Task 3: ElderPane — label transitions and thinking ticker

**Files:**
- Create: `council/app/tui/elder_pane.py`
- Test: `tests/unit/test_elder_pane_labels.py`

This task builds ElderPane's *label-generation logic only*. Round history rendering (which needs a Textual mount context) is added in Task 4.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_elder_pane_labels.py`:

```python
from datetime import datetime, timedelta, timezone

from council.adapters.clock.fake import FakeClock
from council.app.tui.elder_pane import ElderPane
from council.app.tui.verbs import FixedVerbChooser
from council.domain.models import ElderAnswer, ElderError


def _base_clock() -> FakeClock:
    return FakeClock(now=datetime(2026, 4, 19, 12, 0, 0, tzinfo=timezone.utc))


def _answer(elder="claude", agreed=True, text="hi"):
    return ElderAnswer(
        elder=elder,
        text=text,
        error=None,
        agreed=agreed,
        created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
    )


def _error(elder="claude", kind="timeout"):
    return ElderError(elder=elder, kind=kind, detail="")


class TestInitialLabel:
    def test_elder_initial_label_is_display_name_only(self):
        pane = ElderPane.standalone(
            elder_id="claude",
            display_name="Claude",
            verb_chooser=FixedVerbChooser("Pondering"),
            clock=_base_clock(),
        )
        assert pane.current_label() == "Claude"

    def test_synthesis_initial_label_is_synthesis(self):
        pane = ElderPane.standalone(
            elder_id="claude",
            display_name="Synthesis",
            verb_chooser=FixedVerbChooser("Pondering"),
            clock=_base_clock(),
            synthesis=True,
        )
        assert pane.current_label() == "Synthesis"


class TestThinkingLabel:
    def test_elder_thinking_label_has_verb_and_elapsed(self):
        clock = _base_clock()
        pane = ElderPane.standalone(
            elder_id="claude",
            display_name="Claude",
            verb_chooser=FixedVerbChooser("Pondering"),
            clock=clock,
        )
        pane.begin_thinking(round_number=1)
        assert pane.current_label() == "Claude · Pondering… 0s"
        clock.advance_seconds(12)
        pane.refresh_label()
        assert pane.current_label() == "Claude · Pondering… 12s"

    def test_synthesis_thinking_label_has_synthesising_prefix(self):
        clock = _base_clock()
        pane = ElderPane.standalone(
            elder_id="claude",
            display_name="Synthesis",
            verb_chooser=FixedVerbChooser("Pondering"),
            clock=clock,
            synthesis=True,
        )
        pane.begin_thinking(round_number=1)
        clock.advance_seconds(7)
        pane.refresh_label()
        # Synthesis ignores the verb pool — always "Synthesising".
        assert pane.current_label() == "Synthesising… 7s"


class TestCompletedLabel:
    def test_converged_label(self):
        pane = ElderPane.standalone(
            elder_id="claude",
            display_name="Claude",
            verb_chooser=FixedVerbChooser("Pondering"),
            clock=_base_clock(),
        )
        pane.begin_thinking(1)
        pane.end_thinking_completed(_answer(agreed=True))
        assert pane.current_label() == "Claude ✓"

    def test_dissenting_label(self):
        pane = ElderPane.standalone(
            elder_id="claude",
            display_name="Claude",
            verb_chooser=FixedVerbChooser("Pondering"),
            clock=_base_clock(),
        )
        pane.begin_thinking(1)
        pane.end_thinking_completed(_answer(agreed=False))
        assert pane.current_label() == "Claude ↻"

    def test_undeclared_agreement_label_falls_back_to_dissenting(self):
        pane = ElderPane.standalone(
            elder_id="claude",
            display_name="Claude",
            verb_chooser=FixedVerbChooser("Pondering"),
            clock=_base_clock(),
        )
        pane.begin_thinking(1)
        pane.end_thinking_completed(_answer(agreed=None))
        # No explicit agreement — treat as dissent for display purposes.
        assert pane.current_label() == "Claude ↻"

    def test_synthesis_completed_label(self):
        pane = ElderPane.standalone(
            elder_id="claude",
            display_name="Synthesis",
            verb_chooser=FixedVerbChooser("Pondering"),
            clock=_base_clock(),
            synthesis=True,
        )
        pane.begin_thinking(1)
        pane.end_thinking_completed(_answer(agreed=None))
        assert pane.current_label() == "Synthesis ✓"

    def test_error_label(self):
        pane = ElderPane.standalone(
            elder_id="claude",
            display_name="Claude",
            verb_chooser=FixedVerbChooser("Pondering"),
            clock=_base_clock(),
        )
        pane.begin_thinking(1)
        pane.end_thinking_failed(_error(kind="timeout"))
        assert pane.current_label() == "Claude ⚠"


class TestMultipleRounds:
    def test_round_2_rolls_a_fresh_verb(self):
        class CountingChooser:
            def __init__(self):
                self.calls = 0

            def __call__(self):
                self.calls += 1
                return f"Verb{self.calls}"

        clock = _base_clock()
        chooser = CountingChooser()
        pane = ElderPane.standalone(
            elder_id="claude",
            display_name="Claude",
            verb_chooser=chooser,
            clock=clock,
        )
        pane.begin_thinking(1)
        assert pane.current_label() == "Claude · Verb1… 0s"
        pane.end_thinking_completed(_answer(agreed=True))
        pane.begin_thinking(2)
        assert pane.current_label() == "Claude · Verb2… 0s"
        assert chooser.calls == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_elder_pane_labels.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'council.app.tui.elder_pane'`.

- [ ] **Step 3: Implement `council/app/tui/elder_pane.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_elder_pane_labels.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add council/app/tui/elder_pane.py tests/unit/test_elder_pane_labels.py
git commit -m "feat(tui): add ElderPane label state machine (logic-only)"
```

---

## Task 4: ElderPane — Textual widget with history rendering

**Files:**
- Modify: `council/app/tui/elder_pane.py`
- Test: `tests/e2e/test_elder_pane_widget.py`

This wraps the Task 3 logic in a Textual Widget that renders a header, a thinking line, and a history log. Uses `ChronologicalStream` + `format_event` unchanged from Task 17 of the original plan.

- [ ] **Step 1: Write the failing test**

Create `tests/e2e/test_elder_pane_widget.py`:

```python
"""E2E tests for the ElderPaneWidget — must run under a Textual App context
because Widget mount / reactive / query_one all need it."""
from datetime import datetime, timezone

from textual.app import App, ComposeResult

from council.adapters.clock.fake import FakeClock
from council.app.tui.elder_pane import ElderPaneWidget
from council.app.tui.verbs import FixedVerbChooser
from council.domain.models import ElderAnswer, ElderError


def _answer(elder="claude", text="hi", agreed=True):
    return ElderAnswer(
        elder=elder,
        text=text,
        error=None,
        agreed=agreed,
        created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
    )


class _Host(App):
    """Minimal host app for exercising a single ElderPaneWidget."""

    def __init__(self, widget):
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


async def test_widget_appends_completed_turn_to_history():
    clock = FakeClock(now=datetime(2026, 4, 19, 12, tzinfo=timezone.utc))
    widget = ElderPaneWidget(
        elder_id="claude",
        display_name="Claude",
        verb_chooser=FixedVerbChooser("Pondering"),
        clock=clock,
    )
    async with _Host(widget).run_test() as pilot:
        await pilot.pause()
        widget.begin_thinking(round_number=1)
        widget.end_thinking_completed(_answer(text="First round reply"))
        await pilot.pause()
        history = widget.history_text()
        assert "First round reply" in history


async def test_widget_shows_round_divider_from_round_two():
    clock = FakeClock(now=datetime(2026, 4, 19, 12, tzinfo=timezone.utc))
    widget = ElderPaneWidget(
        elder_id="claude",
        display_name="Claude",
        verb_chooser=FixedVerbChooser("Pondering"),
        clock=clock,
    )
    async with _Host(widget).run_test() as pilot:
        await pilot.pause()
        widget.begin_thinking(round_number=1)
        widget.end_thinking_completed(_answer(text="R1 text"))
        await pilot.pause()
        widget.begin_thinking(round_number=2)
        widget.end_thinking_completed(_answer(text="R2 text"))
        await pilot.pause()
        history = widget.history_text()
        assert "R1 text" in history
        assert "R2 text" in history
        assert "Round 2" in history  # divider text somewhere


async def test_widget_renders_failed_turn_in_history():
    clock = FakeClock(now=datetime(2026, 4, 19, 12, tzinfo=timezone.utc))
    widget = ElderPaneWidget(
        elder_id="gemini",
        display_name="Gemini",
        verb_chooser=FixedVerbChooser("Pondering"),
        clock=clock,
    )
    async with _Host(widget).run_test() as pilot:
        await pilot.pause()
        widget.begin_thinking(round_number=1)
        widget.end_thinking_failed(
            ElderError(elder="gemini", kind="quota_exhausted", detail="daily limit")
        )
        await pilot.pause()
        history = widget.history_text()
        assert "quota_exhausted" in history or "ERROR" in history


async def test_synthesis_widget_hides_history_divider_and_placeholder():
    clock = FakeClock(now=datetime(2026, 4, 19, 12, tzinfo=timezone.utc))
    widget = ElderPaneWidget(
        elder_id="claude",
        display_name="Synthesis",
        verb_chooser=FixedVerbChooser("Pondering"),
        clock=clock,
        synthesis=True,
    )
    async with _Host(widget).run_test() as pilot:
        await pilot.pause()
        # Before first synthesis, the placeholder is visible.
        assert "Synthesis runs after" in widget.history_text()
        widget.begin_thinking(round_number=1)
        widget.end_thinking_completed(_answer(text="The final synthesised answer."))
        await pilot.pause()
        history = widget.history_text()
        assert "The final synthesised answer." in history
        # Synthesis doesn't have round dividers.
        assert "Round 2" not in history
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/e2e/test_elder_pane_widget.py -v`
Expected: FAIL with `ImportError: cannot import name 'ElderPaneWidget' from 'council.app.tui.elder_pane'`.

- [ ] **Step 3: Extend `council/app/tui/elder_pane.py`**

Append this code to the existing file (after the `ElderPane` class):

```python
# -------------------------------------------------------------------------
# Textual widget
# -------------------------------------------------------------------------
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import RichLog, Static

from council.adapters.clock.system import SystemClock
from council.app.tui.stream import format_event
from council.app.tui.verbs import RandomVerbChooser
from council.domain.events import TurnCompleted, TurnFailed

_SYNTHESIS_PLACEHOLDER = (
    "[dim]Synthesis runs after you press [bold]s[/] and pick an elder.[/dim]"
)


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
        self._last_round_rendered: int | None = None
        self.label_text = display_name

    def compose(self) -> ComposeResult:
        yield Static("", id="pane-thinking")
        yield RichLog(id="pane-history", markup=True, wrap=True, highlight=False)

    def on_mount(self) -> None:
        if self._synthesis:
            log = self.query_one("#pane-history", RichLog)
            log.write(_SYNTHESIS_PLACEHOLDER)

    # --- state transitions override: sync UI -----------------------------
    def begin_thinking(self, round_number: int) -> None:
        super().begin_thinking(round_number)
        self.label_text = self.current_label()
        self._render_thinking_line()

    def end_thinking_completed(self, answer: ElderAnswer) -> None:
        super().end_thinking_completed(answer)
        self._clear_thinking_line()
        self._append_completed(answer)
        self.label_text = self.current_label()

    def end_thinking_failed(self, error: ElderError) -> None:
        super().end_thinking_failed(error)
        self._clear_thinking_line()
        self._append_failed(error)
        self.label_text = self.current_label()

    def refresh_label(self) -> None:
        self.label_text = self.current_label()
        self._render_thinking_line()

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
        else:
            if self._current_round and self._current_round >= 2 and (
                self._last_round_rendered != self._current_round
            ):
                log.write(f"[dim]─── Round {self._current_round} ───[/dim]")
        log.write(
            format_event(
                TurnCompleted(
                    elder=answer.elder,
                    round_number=self._current_round or 1,
                    answer=answer,
                )
            )
        )
        self._last_round_rendered = self._current_round

    def _append_failed(self, error: ElderError) -> None:
        log = self.query_one("#pane-history", RichLog)
        if not self._synthesis:
            if self._current_round and self._current_round >= 2 and (
                self._last_round_rendered != self._current_round
            ):
                log.write(f"[dim]─── Round {self._current_round} ───[/dim]")
        log.write(
            format_event(
                TurnFailed(
                    elder=error.elder,
                    round_number=self._current_round or 1,
                    error=error,
                )
            )
        )
        self._last_round_rendered = self._current_round

    # --- test helper -----------------------------------------------------
    def history_text(self) -> str:
        log = self.query_one("#pane-history", RichLog)
        # RichLog stores lines as Strip objects; render each to plain text.
        out: list[str] = []
        for line in log.lines:
            out.append(line.text if hasattr(line, "text") else str(line))
        return "\n".join(out)
```

Note: the import block at the top of the file stays the same — these new imports are added below. Consolidate them at the top if ruff complains, but keep them grouped with the Task 3 imports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/e2e/test_elder_pane_widget.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run the full suite to confirm nothing regressed**

Run: `pytest --tb=short -q`
Expected: previous count + 4 e2e + 10 unit (T3) + 5 unit (T1) + 14 unit (T2) passing.

- [ ] **Step 6: Commit**

```bash
git add council/app/tui/elder_pane.py tests/e2e/test_elder_pane_widget.py
git commit -m "feat(tui): add ElderPaneWidget with history rendering"
```

---

## Task 5: CouncilView — responsive layout switcher

**Files:**
- Create: `council/app/tui/council_view.py`
- Test: `tests/e2e/test_council_view_layout.py`

- [ ] **Step 1: Write the failing test**

Create `tests/e2e/test_council_view_layout.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/e2e/test_council_view_layout.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'council.app.tui.council_view'`.

- [ ] **Step 3: Implement `council/app/tui/council_view.py`**

```python
"""Composite widget: holds the four ElderPaneWidgets and switches between
three-column and tabbed layouts based on terminal width."""
from __future__ import annotations

from typing import Literal

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

            async def _mount_panes():
                for key in ("claude", "gemini", "chatgpt", "synthesis"):
                    await tabbed.add_pane(
                        TabPane(self._panes[key].display_name, self._panes[key])
                    )

            # Textual's compose can't be async at this level; we yield the
            # container and add panes in on_mount instead. Simplified here:
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
```

**Note on property access:** `ElderPaneWidget` doesn't currently expose `display_name` as a public property. Add that line to `ElderPaneWidget.__init__` right after `Widget.__init__`:

```python
        self.display_name = display_name
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/e2e/test_council_view_layout.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run the full suite**

Run: `pytest --tb=short -q`
Expected: all previous tests still green plus the 4 new ones.

- [ ] **Step 6: Commit**

```bash
git add council/app/tui/council_view.py council/app/tui/elder_pane.py tests/e2e/test_council_view_layout.py
git commit -m "feat(tui): add CouncilView with responsive layout switcher"
```

---

## Task 6: Add `_pane_lines` e2e helper

**Files:**
- Modify: `tests/e2e/conftest.py` (create if missing)

- [ ] **Step 1: Check whether `tests/e2e/conftest.py` exists**

Run: `ls tests/e2e/conftest.py`
Expected output: either the file path or "No such file". Create in next step regardless.

- [ ] **Step 2: Write `tests/e2e/conftest.py`**

```python
"""Helpers used by e2e tests."""
from __future__ import annotations


def pane_lines(app, elder_key: str) -> str:
    """Return the history text of a specific ElderPaneWidget by elder key.

    `elder_key` is one of "claude", "gemini", "chatgpt", or "synthesis".
    Apps that expose a CouncilView must store it on `app._view`.
    """
    view = getattr(app, "_view", None)
    if view is None:
        raise AssertionError(
            "app has no _view attribute; helper expects CouncilApp-shaped apps"
        )
    pane = view.pane(elder_key)
    return pane.history_text()
```

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/conftest.py
git commit -m "test: add pane_lines helper for per-pane e2e assertions"
```

---

## Task 7: Rewrite CouncilApp around CouncilView

**Files:**
- Modify: `council/app/tui/app.py`
- Modify: `tests/e2e/test_tui_full_debate.py`
- Modify: `tests/e2e/test_tui_health_check_gate.py`

This task rewrites the top-level app to use `CouncilView` instead of `ChronologicalStream`, dispatches bus events to the correct pane, and adjusts the two existing e2e tests that referenced the old flat `rendered_lines` layout.

- [ ] **Step 1: Rewrite `council/app/tui/app.py`**

Overwrite the full file with:

```python
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, RichLog, Static

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.system import SystemClock
from council.adapters.elders.claude_code import ClaudeCodeAdapter
from council.adapters.elders.codex_cli import CodexCLIAdapter
from council.adapters.elders.gemini_cli import GeminiCLIAdapter
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.json_file import JsonFileStore
from council.app.tui.council_view import CouncilView
from council.domain.debate_service import DebateService
from council.domain.events import (
    RoundCompleted,
    SynthesisCompleted,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
)
from council.domain.models import Debate, ElderId
from council.domain.ports import (
    Clock,
    CouncilPackLoader,
    ElderPort,
    TranscriptStore,
)


class SynthesizerModal(ModalScreen[ElderId]):
    BINDINGS = [
        Binding("1", "pick('claude')", "Claude"),
        Binding("2", "pick('gemini')", "Gemini"),
        Binding("3", "pick('chatgpt')", "ChatGPT"),
        Binding("escape", "dismiss(None)", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("Who should synthesize?"),
            Static("[1] Claude   [2] Gemini   [3] ChatGPT   [Esc] Cancel"),
        )

    def action_pick(self, elder: str) -> None:
        self.dismiss(elder)  # type: ignore[arg-type]


class CouncilApp(App):
    CSS = """
    #notices { height: auto; max-height: 6; padding: 0 1; }
    #view { height: 1fr; }
    #input { dock: bottom; }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("c", "continue_round", "Continue", show=False),
        Binding("s", "synthesize", "Synthesize", show=False),
        Binding("a", "abandon", "Abandon", show=False),
        Binding("o", "override", "Override convergence", show=False),
        Binding("f", "toggle_layout", "Toggle layout", show=False),
        Binding("1", "focus_pane('claude')", "Claude", show=False),
        Binding("2", "focus_pane('gemini')", "Gemini", show=False),
        Binding("3", "focus_pane('chatgpt')", "ChatGPT", show=False),
        Binding("4", "focus_pane('synthesis')", "Synthesis", show=False),
    ]

    def __init__(
        self,
        *,
        elders: dict[ElderId, ElderPort],
        store: TranscriptStore,
        clock: Clock,
        pack_loader: CouncilPackLoader,
        pack_name: str,
    ) -> None:
        super().__init__()
        self._elders = elders
        self._store = store
        self._clock = clock
        self._pack_loader = pack_loader
        self._pack_name = pack_name
        self._bus = InMemoryBus()
        self._service = DebateService(elders=elders, store=store, clock=clock, bus=self._bus)
        self._debate: Debate | None = None
        self.awaiting_decision: bool = False
        self.is_finished: bool = False
        self.rendered_lines: list[str] = []  # test-observable notice buffer
        self._tasks: set[asyncio.Task] = set()
        self._view = CouncilView(clock=clock)

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="notices", markup=True, wrap=True, highlight=False)
        yield self._view
        yield Input(placeholder="Ask the council…", id="input")
        yield Footer()

    async def on_mount(self) -> None:
        self._stream_task = self._spawn(self._consume_events())
        self.query_one("#input", Input).focus()
        self._spawn(self._run_health_checks())

    async def on_unmount(self) -> None:
        if hasattr(self, "_stream_task"):
            self._stream_task.cancel()
        for task in list(self._tasks):
            task.cancel()

    # --- event fan-out ---------------------------------------------------
    async def _consume_events(self) -> None:
        async for ev in self._bus.subscribe():
            if isinstance(ev, TurnStarted):
                self._view.pane(ev.elder).begin_thinking(ev.round_number)
            elif isinstance(ev, TurnCompleted):
                self._view.pane(ev.elder).end_thinking_completed(ev.answer)
            elif isinstance(ev, TurnFailed):
                self._view.pane(ev.elder).end_thinking_failed(ev.error)
            elif isinstance(ev, RoundCompleted):
                self.awaiting_decision = True
            elif isinstance(ev, SynthesisCompleted):
                self._view.pane("synthesis").end_thinking_completed(ev.answer)
                self._view.pane("synthesis").focus()
                self.is_finished = True
                self.awaiting_decision = False

    # --- health check ----------------------------------------------------
    async def _run_health_checks(self) -> None:
        labels: dict[ElderId, str] = {
            "claude": "Claude",
            "gemini": "Gemini",
            "chatgpt": "ChatGPT",
        }

        async def _probe(elder_id: ElderId) -> tuple[ElderId, bool]:
            try:
                ok = await self._elders[elder_id].health_check()
            except Exception:
                ok = False
            return elder_id, ok

        results = await asyncio.gather(*(_probe(eid) for eid in self._elders))
        unhealthy = [eid for eid, ok in results if not ok]
        if not unhealthy:
            return
        for eid in unhealthy:
            self._write_notice(
                f"[yellow]⚠ {labels[eid]} CLI is unavailable or unauthenticated. "
                f"Install it and run its `login` command before asking a question.[/yellow]"
            )
        if len(unhealthy) == len(self._elders):
            self.query_one("#input", Input).disabled = True
            self._write_notice(
                "[red]No elders available. Fix the vendor CLI setup above, "
                "then restart the app.[/red]"
            )

    def _write_notice(self, line: str) -> None:
        self.rendered_lines.append(line)
        self.query_one("#notices", RichLog).write(line)

    # --- user actions ----------------------------------------------------
    @on(Input.Submitted, "#input")
    async def _on_prompt_submitted(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        if not prompt or self._debate is not None:
            return
        pack = self._pack_loader.load(self._pack_name)
        self._debate = Debate(
            id=str(uuid.uuid4()),
            prompt=prompt,
            pack=pack,
            rounds=[],
            status="in_progress",
            synthesis=None,
        )
        input_widget = self.query_one("#input", Input)
        input_widget.disabled = True
        # Move focus onto the first elder pane.
        self._view.pane("claude").focus()
        self._spawn(self._service.run_round(self._debate))

    async def action_continue_round(self) -> None:
        if not self.awaiting_decision or self._debate is None:
            return
        self.awaiting_decision = False
        self._spawn(self._service.run_round(self._debate))

    async def action_abandon(self) -> None:
        if self._debate is None:
            return
        self._debate.status = "abandoned"
        self.is_finished = True
        self.awaiting_decision = False
        self.exit()

    async def action_override(self) -> None:
        if not self.awaiting_decision or not self._debate or not self._debate.rounds:
            return
        from dataclasses import replace

        from council.domain.models import Turn

        r = self._debate.rounds[-1]
        r.turns = [Turn(elder=t.elder, answer=replace(t.answer, agreed=True)) for t in r.turns]

    async def action_synthesize(self) -> None:
        if not self.awaiting_decision or self._debate is None:
            return
        self.run_worker(self._synthesize_worker(), exclusive=True)

    async def _synthesize_worker(self) -> None:
        if self._debate is None:
            return
        choice = await self.push_screen_wait(SynthesizerModal())
        if choice is None:
            return
        self.awaiting_decision = False
        self._view.pane("synthesis").begin_thinking(round_number=1)
        self._spawn(self._service.synthesize(self._debate, by=choice))

    async def action_toggle_layout(self) -> None:
        self._view.toggle_forced_mode()

    async def action_focus_pane(self, key: str) -> None:
        try:
            self._view.pane(key).focus()
        except KeyError:
            pass


def main() -> None:
    import argparse
    import os

    parser = argparse.ArgumentParser(prog="council")
    parser.add_argument("--pack", default="bare")
    parser.add_argument("--packs-root", default=str(Path.home() / ".council" / "packs"))
    parser.add_argument("--store-root", default=str(Path.home() / ".council" / "debates"))
    parser.add_argument(
        "--claude-model",
        default=os.environ.get("COUNCIL_CLAUDE_MODEL"),
        help="Model alias or full name passed to `claude --model` (e.g. sonnet, opus).",
    )
    parser.add_argument(
        "--gemini-model",
        default=os.environ.get("COUNCIL_GEMINI_MODEL"),
        help="Model name passed to `gemini -m` (e.g. gemini-2.5-flash — recommended; Pro has tight quota).",
    )
    parser.add_argument(
        "--codex-model",
        default=os.environ.get("COUNCIL_CODEX_MODEL"),
        help="Model name passed to `codex exec -m` (e.g. gpt-5-codex).",
    )
    args = parser.parse_args()

    packs_root = Path(args.packs_root)
    packs_root.mkdir(parents=True, exist_ok=True)
    (packs_root / args.pack).mkdir(exist_ok=True)  # ensure bare pack works

    app = CouncilApp(
        elders={
            "claude": ClaudeCodeAdapter(model=args.claude_model),
            "gemini": GeminiCLIAdapter(model=args.gemini_model),
            "chatgpt": CodexCLIAdapter(model=args.codex_model),
        },
        store=JsonFileStore(root=Path(args.store_root)),
        clock=SystemClock(),
        pack_loader=FilesystemPackLoader(root=packs_root),
        pack_name=args.pack,
    )
    app.run()
```

- [ ] **Step 2: Rewrite `tests/e2e/test_tui_full_debate.py`**

Overwrite with:

```python
import asyncio
from datetime import datetime, timezone

from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.in_memory import InMemoryStore
from council.app.tui.app import CouncilApp
from tests.e2e.conftest import pane_lines


async def _wait_until(pilot, predicate, *, timeout_s=5.0, tick=0.05):
    elapsed = 0.0
    while not predicate():
        await pilot.pause()
        await asyncio.sleep(tick)
        elapsed += tick
        if elapsed > timeout_s:
            raise AssertionError(f"Timed out; elapsed={elapsed:.2f}s")


async def test_full_debate_via_tui(tmp_path):
    (tmp_path / "bare").mkdir()
    loader = FilesystemPackLoader(root=tmp_path)

    elders = {
        "claude": FakeElder(
            elder_id="claude",
            replies=[
                "R1 Claude\nCONVERGED: yes",
                "Final synthesised answer.",
            ],
        ),
        "gemini": FakeElder(
            elder_id="gemini", replies=["R1 Gemini\nCONVERGED: yes"]
        ),
        "chatgpt": FakeElder(
            elder_id="chatgpt", replies=["R1 ChatGPT\nCONVERGED: yes"]
        ),
    }
    app = CouncilApp(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 19, tzinfo=timezone.utc)),
        pack_loader=loader,
        pack_name="bare",
    )

    async with app.run_test() as pilot:
        await pilot.press(*"What should I do?")
        await pilot.press("enter")
        await _wait_until(pilot, lambda: app.awaiting_decision)

        await pilot.press("s")
        await _wait_until(pilot, lambda: len(app.screen_stack) > 1, timeout_s=2.0)
        await pilot.press("1")  # pick Claude as synthesiser
        await _wait_until(pilot, lambda: app.is_finished)

        assert "R1 Claude" in pane_lines(app, "claude")
        assert "R1 Gemini" in pane_lines(app, "gemini")
        assert "R1 ChatGPT" in pane_lines(app, "chatgpt")
        assert "Final synthesised answer." in pane_lines(app, "synthesis")
```

- [ ] **Step 3: Adjust `tests/e2e/test_tui_health_check_gate.py`**

Open the file and replace the import block at the top:

```python
import asyncio
from datetime import datetime, timezone

from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.in_memory import InMemoryStore
from council.app.tui.app import CouncilApp
```

The test body already asserts on `app.rendered_lines`, which is preserved in the rewritten app. No other changes needed unless ruff complains about unused imports.

- [ ] **Step 4: Run all tests**

Run: `pytest --tb=short -q`
Expected: all passing. Previous counts plus the new Task 4 and Task 5 tests.

- [ ] **Step 5: Commit**

```bash
git add council/app/tui/app.py tests/e2e/test_tui_full_debate.py tests/e2e/test_tui_health_check_gate.py
git commit -m "refactor(tui): rewrite CouncilApp around CouncilView and ElderPanes"
```

---

## Task 8: E2E — tab navigation

**Files:**
- Create: `tests/e2e/test_tui_tab_navigation.py`

- [ ] **Step 1: Write the failing test**

```python
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
        await pilot.press("enter")
        await _wait_until(pilot, lambda: app.awaiting_decision)

        for key, elder in [("2", "gemini"), ("3", "chatgpt"), ("4", "synthesis"), ("1", "claude")]:
            await pilot.press(key)
            await pilot.pause()
            assert app._view.pane(elder).has_focus
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/e2e/test_tui_tab_navigation.py -v`
Expected: FAIL — depending on state of `_view.pane(...).has_focus`; assertion should catch it.

- [ ] **Step 3: If the assertion fails, use the columns-mode variant of the test**

`can_focus = True` was added to `ElderPaneWidget` in Task 4, so panes can accept focus. If Textual in tabs mode routes focus through the `TabbedContent` instead of the pane widget, the assertion `has_focus` on the pane is still correct — the tabbed-content wrapper delegates focus to its active pane. If the test still fails, force columns mode by running `run_test(size=(300, 40))` so focus maps directly to the pane widget. Update the `run_test` call in Step 1 to use `size=(300, 40)` and re-run.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/e2e/test_tui_tab_navigation.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/test_tui_tab_navigation.py
git commit -m "test(tui): add tab navigation e2e"
```

---

## Task 9: E2E — per-elder history

**Files:**
- Create: `tests/e2e/test_tui_history_per_elder.py`

- [ ] **Step 1: Write the failing test**

```python
import asyncio
from datetime import datetime, timezone

from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.in_memory import InMemoryStore
from council.app.tui.app import CouncilApp
from tests.e2e.conftest import pane_lines


async def _wait_until(pilot, predicate, *, timeout_s=5.0, tick=0.05):
    elapsed = 0.0
    while not predicate():
        await pilot.pause()
        await asyncio.sleep(tick)
        elapsed += tick
        if elapsed > timeout_s:
            raise AssertionError(f"Timed out; elapsed={elapsed:.2f}s")


async def test_two_rounds_appear_in_each_elder_pane_with_divider(tmp_path):
    (tmp_path / "bare").mkdir()
    elders = {
        "claude": FakeElder(
            elder_id="claude",
            replies=["R1 Claude text\nCONVERGED: no", "R2 Claude text\nCONVERGED: yes"],
        ),
        "gemini": FakeElder(
            elder_id="gemini",
            replies=["R1 Gemini text\nCONVERGED: no", "R2 Gemini text\nCONVERGED: yes"],
        ),
        "chatgpt": FakeElder(
            elder_id="chatgpt",
            replies=["R1 ChatGPT text\nCONVERGED: no", "R2 ChatGPT text\nCONVERGED: yes"],
        ),
    }
    app = CouncilApp(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 19, tzinfo=timezone.utc)),
        pack_loader=FilesystemPackLoader(root=tmp_path),
        pack_name="bare",
    )
    async with app.run_test() as pilot:
        await pilot.press(*"Two rounds?")
        await pilot.press("enter")
        await _wait_until(pilot, lambda: app.awaiting_decision)
        # First round landed.  action_continue_round sets awaiting_decision=False
        # before spawning round 2; the bus consumer flips it back to True
        # when RoundCompleted for round 2 fires.
        await pilot.press("c")
        await _wait_until(pilot, lambda: not app.awaiting_decision, timeout_s=2.0)
        await _wait_until(pilot, lambda: app.awaiting_decision)

        for elder, r1_text, r2_text in [
            ("claude", "R1 Claude text", "R2 Claude text"),
            ("gemini", "R1 Gemini text", "R2 Gemini text"),
            ("chatgpt", "R1 ChatGPT text", "R2 ChatGPT text"),
        ]:
            text = pane_lines(app, elder)
            assert r1_text in text
            assert r2_text in text
            assert "Round 2" in text
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/e2e/test_tui_history_per_elder.py -v`
Expected: PASS. The divider rendering was implemented in Task 4; the two-phase wait (`not awaiting_decision` then `awaiting_decision`) correctly follows the round-2 lifecycle.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_tui_history_per_elder.py
git commit -m "test(tui): add per-elder history e2e with round divider"
```

---

## Task 10: E2E — layout mode toggle

**Files:**
- Create: `tests/e2e/test_tui_layout_toggle.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/e2e/test_tui_layout_toggle.py -v`
Expected: PASS (all machinery implemented by Tasks 5 and 7).

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_tui_layout_toggle.py
git commit -m "test(tui): add layout mode toggle e2e"
```

---

## Task 11: Polish — ruff, full suite, README note

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run lint + format**

Run:
```bash
source .venv/bin/activate
ruff check council/ tests/ --fix
ruff format council/ tests/
```

- [ ] **Step 2: Full test suite**

Run: `pytest -v`
Expected: all passing; integration tests deselected by default.

- [ ] **Step 3: Update `README.md`**

Find the keybindings table section:

```markdown
## Keybindings during a debate

| Key | Action |
|---|---|
| `c` | Continue another round — elders see each other's answers |
| `s` | Synthesise — pick who writes the final answer |
| `a` | Abandon |
| `o` | Override convergence |
```

Replace with:

```markdown
## Keybindings during a debate

| Key | Action |
|---|---|
| `c` | Continue another round — elders see each other's answers |
| `s` | Synthesise — pick who writes the final answer |
| `a` | Abandon |
| `o` | Override convergence |
| `1` / `2` / `3` / `4` | Jump to Claude / Gemini / ChatGPT / Synthesis pane |
| `Tab` / `Shift+Tab` | Cycle forward / backward through panes |
| `f` | Toggle layout: auto → force tabs → force columns → auto |

The layout automatically uses three columns when the terminal is at least 240 characters wide (80 per elder) and tabs otherwise. Press `f` to override.
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: describe new tab / column keybindings in README"
```

- [ ] **Step 5: Push**

```bash
git push
```

---

## Spec coverage audit

| Spec section | Covered by |
|---|---|
| Three-column when ≥240 cols, tabs below, `f` override | Tasks 2, 5, 7, 10 |
| Number keys `1/2/3/4` + Tab/Shift+Tab | Tasks 7, 8 |
| Per-elder full round history with dividers | Tasks 4, 9 |
| Synthesis pane always present, placeholder, full-width | Tasks 4, 5, 7 |
| Thinking UX: elapsed counter + rotating verb | Tasks 1, 3, 4 |
| Verb pool (12 verbs, shared) | Task 1 |
| Tab labels (`Claude ✓`/`↻`/`⚠`/`· Pondering… 12s`) | Tasks 3, 4 |
| Global keys `c`/`s`/`a`/`o` unchanged | Task 7 |
| `ElderPane` widget + `ChronologicalStream` reuse | Tasks 3, 4 |
| `CouncilView` layout switcher | Task 5 |
| `CouncilApp` rewired as plumbing | Task 7 |
| System notices area (health check) | Task 7 |
| `_pane_lines` test helper | Task 6 |
| Tests: threshold unit, label transitions unit, verb chooser unit, three e2e, two edited e2e | Tasks 1, 2, 3, 4, 5, 7, 8, 9, 10 |

No gaps.

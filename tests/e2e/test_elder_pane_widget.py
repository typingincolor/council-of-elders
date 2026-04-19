"""E2E tests for the ElderPaneWidget — must run under a Textual App context
because Widget mount / reactive / query_one all need it."""

from datetime import datetime, timezone

from textual.app import App, ComposeResult

from council.adapters.clock.fake import FakeClock
from council.app.tui.elder_pane import ElderPaneWidget
from council.app.tui.verbs import FixedVerbChooser
from council.domain.models import ElderAnswer, ElderError, ElderQuestion, UserMessage


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


async def test_widget_label_updates_while_thinking():
    """When a turn is in flight, the elapsed seconds should advance."""
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
        await pilot.pause()
        assert widget.label_text == "Claude · Pondering… 0s"
        # Advance the fake clock; the ticker calls refresh_label which reads
        # the clock via current_label().
        clock.advance_seconds(7)
        widget.refresh_label()
        assert widget.label_text == "Claude · Pondering… 7s"


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


async def test_widget_renders_user_message_inline():
    clock = FakeClock(now=datetime(2026, 4, 19, 12, tzinfo=timezone.utc))
    widget = ElderPaneWidget(
        elder_id="claude",
        display_name="Claude",
        verb_chooser=FixedVerbChooser("Pondering"),
        clock=clock,
    )
    async with _Host(widget).run_test() as pilot:
        await pilot.pause()
        widget.begin_thinking(1)
        widget.end_thinking_completed(_answer(text="R1 answer"))
        await pilot.pause()
        widget.on_user_message(
            UserMessage(
                text="please clarify scope",
                after_round=1,
                created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
            )
        )
        await pilot.pause()
        history = widget.history_text()
        assert "R1 answer" in history
        assert "please clarify scope" in history
        assert "You" in history


async def test_widget_renders_asker_question_in_asker_pane():
    """Claude's pane shows Claude's own outgoing questions as '[To Gemini] …'."""
    clock = FakeClock(now=datetime(2026, 4, 19, 12, tzinfo=timezone.utc))
    widget = ElderPaneWidget(
        elder_id="claude",
        display_name="Claude",
        verb_chooser=FixedVerbChooser("Pondering"),
        clock=clock,
    )
    async with _Host(widget).run_test() as pilot:
        await pilot.pause()
        widget.begin_thinking(1)
        q = ElderQuestion(
            from_elder="claude", to_elder="gemini",
            text="timeline?", round_number=1
        )
        widget.end_thinking_completed(
            _answer(text="My answer"), questions=(q,)
        )
        await pilot.pause()
        history = widget.history_text()
        assert "My answer" in history
        assert "To Gemini" in history
        assert "timeline?" in history


async def test_widget_renders_incoming_question_in_target_pane():
    """Gemini's pane shows Claude's question TO Gemini as '[From Claude] …'."""
    clock = FakeClock(now=datetime(2026, 4, 19, 12, tzinfo=timezone.utc))
    widget = ElderPaneWidget(
        elder_id="gemini",
        display_name="Gemini",
        verb_chooser=FixedVerbChooser("Pondering"),
        clock=clock,
    )
    async with _Host(widget).run_test() as pilot:
        await pilot.pause()
        q = ElderQuestion(
            from_elder="claude", to_elder="gemini",
            text="timeline?", round_number=1
        )
        widget.on_incoming_question(q)
        await pilot.pause()
        history = widget.history_text()
        assert "From Claude" in history
        assert "timeline?" in history

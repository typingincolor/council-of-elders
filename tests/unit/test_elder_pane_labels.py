from datetime import datetime, timezone

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

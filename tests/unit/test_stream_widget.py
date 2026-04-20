from datetime import datetime, timezone

from council.app.tui.stream import format_event
from council.domain.events import (
    RoundCompleted,
    SynthesisCompleted,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
)
from council.domain.models import ElderAnswer, ElderError, Round


def _answer(elder="ada", text="hi"):
    return ElderAnswer(
        elder=elder,
        text=text,
        error=None,
        agreed=True,
        created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )


def test_turn_started_renders_status_line():
    s = format_event(TurnStarted(elder="ada", round_number=1))
    assert "Ada" in s
    assert "round 1" in s.lower()


def test_turn_completed_renders_with_label():
    s = format_event(TurnCompleted(elder="kai", round_number=1, answer=_answer("kai", "gx")))
    assert "[Kai]" in s
    assert "gx" in s


def test_turn_failed_renders_error():
    err = ElderError(elder="mei", kind="timeout", detail="")
    s = format_event(TurnFailed(elder="mei", round_number=1, error=err))
    assert "Mei" in s
    assert "timeout" in s.lower()


def test_round_completed_renders_divider():
    r = Round(number=2, turns=[])
    s = format_event(RoundCompleted(round=r))
    assert "Round 2 complete" in s


def test_synthesis_renders_with_label():
    s = format_event(SynthesisCompleted(answer=_answer("ada", "final")))
    assert "[Synthesis" in s
    assert "final" in s

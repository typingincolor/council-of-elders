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


def _answer(elder="claude", text="hi"):
    return ElderAnswer(
        elder=elder,
        text=text,
        error=None,
        agreed=True,
        created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )


def test_turn_started_renders_status_line():
    s = format_event(TurnStarted(elder="claude", round_number=1))
    assert "Claude" in s
    assert "round 1" in s.lower()


def test_turn_completed_renders_with_label():
    s = format_event(TurnCompleted(elder="gemini", round_number=1, answer=_answer("gemini", "gx")))
    assert "[Gemini]" in s
    assert "gx" in s


def test_turn_failed_renders_error():
    err = ElderError(elder="chatgpt", kind="timeout", detail="")
    s = format_event(TurnFailed(elder="chatgpt", round_number=1, error=err))
    assert "ChatGPT" in s
    assert "timeout" in s.lower()


def test_round_completed_renders_divider():
    r = Round(number=2, turns=[])
    s = format_event(RoundCompleted(round=r))
    assert "Round 2 complete" in s


def test_synthesis_renders_with_label():
    s = format_event(SynthesisCompleted(answer=_answer("claude", "final")))
    assert "[Synthesis" in s
    assert "final" in s

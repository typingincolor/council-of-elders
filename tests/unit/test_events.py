from datetime import datetime, timezone
from council.domain.events import (
    DebateAbandoned,
    DebateEvent,
    RoundCompleted,
    SynthesisCompleted,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
)
from council.domain.models import ElderAnswer, ElderError, Round


def test_turn_started_is_debate_event():
    e: DebateEvent = TurnStarted(elder="claude", round_number=1)
    assert e.elder == "claude"
    assert e.round_number == 1


def test_turn_completed_carries_answer():
    ans = ElderAnswer(
        elder="claude",
        text="hi",
        error=None,
        agreed=True,
        created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )
    e = TurnCompleted(elder="claude", round_number=1, answer=ans)
    assert e.answer is ans


def test_turn_failed_carries_error():
    err = ElderError(elder="claude", kind="timeout", detail="")
    e = TurnFailed(elder="claude", round_number=1, error=err)
    assert e.error is err


def test_round_completed_carries_round():
    r = Round(number=1, turns=[])
    e = RoundCompleted(round=r)
    assert e.round is r


def test_synthesis_and_abandoned_shapes():
    ans = ElderAnswer(
        elder="claude",
        text="final",
        error=None,
        agreed=None,
        created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )
    assert SynthesisCompleted(answer=ans).answer is ans
    assert DebateAbandoned().__class__.__name__ == "DebateAbandoned"


def test_user_message_received_carries_message():
    from council.domain.events import UserMessageReceived
    from council.domain.models import UserMessage

    m = UserMessage(
        text="clarify please",
        after_round=1,
        created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
    )
    e = UserMessageReceived(message=m)
    assert e.message is m

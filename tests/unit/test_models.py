from datetime import datetime, timezone
import pytest
from council.domain.models import (
    CouncilPack,
    Debate,
    ElderAnswer,
    ElderError,
    Round,
    Turn,
)


def _answer(elder="claude", agreed=None, text="hello", error=None):
    return ElderAnswer(
        elder=elder,
        text=text,
        error=error,
        agreed=agreed,
        created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )


class TestRound:
    def test_converged_true_when_three_elders_all_agreed(self):
        r = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_answer("claude", agreed=True)),
                Turn(elder="gemini", answer=_answer("gemini", agreed=True)),
                Turn(elder="chatgpt", answer=_answer("chatgpt", agreed=True)),
            ],
        )
        assert r.converged() is True

    def test_converged_false_when_any_disagreed(self):
        r = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_answer("claude", agreed=True)),
                Turn(elder="gemini", answer=_answer("gemini", agreed=False)),
                Turn(elder="chatgpt", answer=_answer("chatgpt", agreed=True)),
            ],
        )
        assert r.converged() is False

    def test_converged_false_when_any_undeclared(self):
        r = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_answer("claude", agreed=True)),
                Turn(elder="gemini", answer=_answer("gemini", agreed=None)),
                Turn(elder="chatgpt", answer=_answer("chatgpt", agreed=True)),
            ],
        )
        assert r.converged() is False

    def test_converged_false_with_fewer_than_three_turns(self):
        r = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_answer("claude", agreed=True)),
                Turn(elder="gemini", answer=_answer("gemini", agreed=True)),
            ],
        )
        assert r.converged() is False

    def test_converged_false_when_elders_are_duplicates(self):
        r = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_answer("claude", agreed=True)),
                Turn(elder="claude", answer=_answer("claude", agreed=True)),
                Turn(elder="claude", answer=_answer("claude", agreed=True)),
            ],
        )
        assert r.converged() is False


class TestCouncilPack:
    def test_empty_pack_has_no_overrides(self):
        pack = CouncilPack(name="bare", shared_context=None, personas={})
        assert pack.personas == {}
        assert pack.shared_context is None


class TestElderAnswer:
    def test_can_hold_only_error(self):
        err = ElderError(elder="claude", kind="timeout", detail="")
        a = _answer(error=err, text=None)
        assert a.text is None
        assert a.error is err


class TestDebate:
    def test_new_debate_has_no_rounds(self):
        pack = CouncilPack(name="bare", shared_context=None, personas={})
        d = Debate(id="abc", prompt="hi", pack=pack, rounds=[], status="in_progress", synthesis=None)
        assert d.rounds == []
        assert d.status == "in_progress"

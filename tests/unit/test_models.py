from datetime import datetime, timezone
import pytest
from council.domain.models import (
    CouncilPack,
    Debate,
    ElderAnswer,
    ElderError,
    ElderQuestion,
    Round,
    Turn,
    UserMessage,
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
        d = Debate(
            id="abc", prompt="hi", pack=pack, rounds=[], status="in_progress", synthesis=None
        )
        assert d.rounds == []
        assert d.status == "in_progress"


class TestUserMessage:
    def test_construct_with_expected_fields(self):
        m = UserMessage(
            text="clarify scope please",
            after_round=1,
            created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
        )
        assert m.text == "clarify scope please"
        assert m.after_round == 1

    def test_is_frozen(self):
        m = UserMessage(
            text="x",
            after_round=0,
            created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
        )
        with pytest.raises(Exception):
            m.text = "y"  # type: ignore[misc]


class TestElderQuestion:
    def test_construct_with_expected_fields(self):
        q = ElderQuestion(
            from_elder="claude",
            to_elder="gemini",
            text="Have you considered X?",
            round_number=1,
        )
        assert q.from_elder == "claude"
        assert q.to_elder == "gemini"

    def test_is_frozen(self):
        q = ElderQuestion(
            from_elder="claude", to_elder="gemini", text="x", round_number=1
        )
        with pytest.raises(Exception):
            q.text = "y"  # type: ignore[misc]


class TestDebateUserMessages:
    def test_fresh_debate_has_empty_user_messages(self):
        pack = CouncilPack(name="bare", shared_context=None, personas={})
        d = Debate(
            id="d1",
            prompt="?",
            pack=pack,
            rounds=[],
            status="in_progress",
            synthesis=None,
        )
        assert d.user_messages == []


class TestTurnQuestions:
    def test_fresh_turn_has_empty_questions(self):
        t = Turn(
            elder="claude",
            answer=ElderAnswer(
                elder="claude",
                text="hi",
                error=None,
                agreed=True,
                created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
            ),
        )
        assert t.questions == ()

    def test_turn_with_questions(self):
        q = ElderQuestion(
            from_elder="claude", to_elder="gemini", text="?", round_number=1
        )
        t = Turn(
            elder="claude",
            answer=ElderAnswer(
                elder="claude",
                text="hi",
                error=None,
                agreed=True,
                created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
            ),
            questions=(q,),
        )
        assert len(t.questions) == 1

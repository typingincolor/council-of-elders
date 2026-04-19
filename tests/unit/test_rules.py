from datetime import datetime, timezone

import pytest

from council.domain.models import (
    CouncilPack,
    Debate,
    ElderAnswer,
    Round,
    Turn,
)
from council.domain.rules import DefaultRules, ValidationOk, Violation


def _answer(elder, text="x", agreed=None):
    return ElderAnswer(
        elder=elder,
        text=text,
        error=None,
        agreed=agreed,
        created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
    )


def _debate(rounds=None):
    return Debate(
        id="d",
        prompt="Q?",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=rounds or [],
        status="in_progress",
        synthesis=None,
    )


def _filled_r1():
    return Round(
        number=1,
        turns=[
            Turn(elder="claude", answer=_answer("claude", "c")),
            Turn(elder="gemini", answer=_answer("gemini", "g")),
            Turn(elder="chatgpt", answer=_answer("chatgpt", "ct")),
        ],
    )


def _filled_r2():
    return Round(
        number=2,
        turns=[
            Turn(elder="claude", answer=_answer("claude", "c2")),
            Turn(elder="gemini", answer=_answer("gemini", "g2")),
            Turn(elder="chatgpt", answer=_answer("chatgpt", "ct2")),
        ],
    )


@pytest.fixture
def rules():
    return DefaultRules()


class TestDefaultRulesDispatch:
    def test_user_message_dispatches_on_round_1(self, rules):
        out = rules.user_message(_debate(), "claude", 1)
        assert "initial take" in out.lower()
        assert "CONVERGED" not in out

    def test_user_message_dispatches_on_round_2(self, rules):
        out = rules.user_message(_debate([_filled_r1()]), "claude", 2)
        assert "QUESTIONS:" in out

    def test_user_message_dispatches_on_round_3_plus(self, rules):
        out = rules.user_message(_debate([_filled_r1(), _filled_r2()]), "claude", 3)
        assert "CONVERGED: yes" in out

    def test_user_message_dispatches_on_large_round_numbers(self, rules):
        # Synthesise a debate with enough rounds to satisfy the round_n prompt builder.
        rounds = [_filled_r1(), _filled_r2()]
        for i in range(3, 7):
            rounds.append(
                Round(
                    number=i,
                    turns=[
                        Turn(elder="claude", answer=_answer("claude", f"c{i}", agreed=False)),
                        Turn(elder="gemini", answer=_answer("gemini", f"g{i}", agreed=False)),
                        Turn(elder="chatgpt", answer=_answer("chatgpt", f"ct{i}", agreed=False)),
                    ],
                )
            )
        out = rules.user_message(_debate(rounds), "claude", 7)
        assert "CONVERGED: yes" in out


class TestDefaultRulesValidation:
    def test_ok_in_round_1(self, rules):
        r = rules.validate(agreed=None, questions=(), round_num=1, from_elder="claude")
        assert isinstance(r, ValidationOk)

    def test_violation_in_round_1(self, rules):
        r = rules.validate(agreed=True, questions=(), round_num=1, from_elder="claude")
        assert isinstance(r, Violation)
        assert r.reason == "r1_unexpected_convergence"


class TestDefaultRulesRetry:
    def test_retry_reminder_uses_violation_detail(self, rules):
        v = Violation(reason="test", detail="this is the specific reason")
        out = rules.retry_reminder(v)
        assert "this is the specific reason" in out


class TestDefaultRulesConvergence:
    def test_is_converged_true_when_all_agreed(self, rules):
        r = Round(
            number=3,
            turns=[
                Turn(elder="claude", answer=_answer("claude", "x", agreed=True)),
                Turn(elder="gemini", answer=_answer("gemini", "x", agreed=True)),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "x", agreed=True)),
            ],
        )
        assert rules.is_converged(r) is True

    def test_is_converged_false_when_any_disagree(self, rules):
        r = Round(
            number=3,
            turns=[
                Turn(elder="claude", answer=_answer("claude", "x", agreed=True)),
                Turn(elder="gemini", answer=_answer("gemini", "x", agreed=False)),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "x", agreed=True)),
            ],
        )
        assert rules.is_converged(r) is False

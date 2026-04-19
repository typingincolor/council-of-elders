import pytest

from council.domain.models import ElderQuestion
from council.domain.validation import TurnValidator, ValidationOk, Violation


@pytest.fixture
def validator():
    return TurnValidator()


def _q(from_elder="claude", to_elder="gemini", text="why?", round_number=2):
    return ElderQuestion(
        from_elder=from_elder,
        to_elder=to_elder,
        text=text,
        round_number=round_number,
    )


class TestRoundOne:
    def test_ok_with_nothing_extra(self, validator):
        r = validator.validate(agreed=None, questions=(), round_num=1, from_elder="claude")
        assert isinstance(r, ValidationOk)

    def test_unexpected_convergence(self, validator):
        r = validator.validate(agreed=True, questions=(), round_num=1, from_elder="claude")
        assert isinstance(r, Violation)
        assert r.reason == "r1_unexpected_convergence"

    def test_unexpected_questions(self, validator):
        r = validator.validate(
            agreed=None,
            questions=(_q(round_number=1),),
            round_num=1,
            from_elder="claude",
        )
        assert isinstance(r, Violation)
        assert r.reason == "r1_unexpected_questions"


class TestRoundTwo:
    def test_ok_with_one_peer_question(self, validator):
        r = validator.validate(agreed=None, questions=(_q(),), round_num=2, from_elder="claude")
        assert isinstance(r, ValidationOk)

    def test_missing_question(self, validator):
        r = validator.validate(agreed=None, questions=(), round_num=2, from_elder="claude")
        assert isinstance(r, Violation)
        assert r.reason == "r2_missing_question"

    def test_multiple_questions(self, validator):
        qs = (_q(to_elder="gemini"), _q(to_elder="chatgpt"))
        r = validator.validate(agreed=None, questions=qs, round_num=2, from_elder="claude")
        assert isinstance(r, Violation)
        assert r.reason == "r2_multiple_questions"

    def test_unexpected_convergence(self, validator):
        r = validator.validate(agreed=True, questions=(_q(),), round_num=2, from_elder="claude")
        assert isinstance(r, Violation)
        assert r.reason == "r2_unexpected_convergence"


class TestRoundThreePlus:
    @pytest.mark.parametrize("n", [3, 5, 12])
    def test_ok_converged_yes(self, validator, n):
        r = validator.validate(agreed=True, questions=(), round_num=n, from_elder="claude")
        assert isinstance(r, ValidationOk)

    def test_ok_converged_no_with_question(self, validator):
        r = validator.validate(
            agreed=False,
            questions=(_q(round_number=3),),
            round_num=3,
            from_elder="claude",
        )
        assert isinstance(r, ValidationOk)

    def test_missing_convergence(self, validator):
        r = validator.validate(agreed=None, questions=(), round_num=3, from_elder="claude")
        assert isinstance(r, Violation)
        assert r.reason == "rn_missing_convergence"

    def test_no_with_missing_question(self, validator):
        r = validator.validate(agreed=False, questions=(), round_num=3, from_elder="claude")
        assert isinstance(r, Violation)
        assert r.reason == "rn_no_converged_missing_question"

    def test_no_with_multiple_questions(self, validator):
        qs = (
            _q(to_elder="gemini", round_number=3),
            _q(to_elder="chatgpt", round_number=3),
        )
        r = validator.validate(agreed=False, questions=qs, round_num=3, from_elder="claude")
        assert isinstance(r, Violation)
        assert r.reason == "rn_multiple_questions"

    def test_yes_with_question_not_a_violation(self, validator):
        # yes+question is "drop with warn" territory — validator returns OK,
        # DebateService discards the question.
        r = validator.validate(
            agreed=True,
            questions=(_q(round_number=3),),
            round_num=3,
            from_elder="claude",
        )
        assert isinstance(r, ValidationOk)

"""Tests for SilentReviseRules — the alternative debate-rules policy
used by the format ablation.
"""

from datetime import datetime, timezone

from council.domain.models import CouncilPack, Debate, ElderQuestion, Round, Turn
from council.domain.models import ElderAnswer
from council.domain.rules import SilentReviseRules, ValidationOk, Violation


def _debate(prompt: str = "Q?") -> Debate:
    return Debate(
        id="t",
        prompt=prompt,
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[],
        status="in_progress",
        synthesis=None,
    )


def _r1() -> Round:
    t = datetime(2026, 4, 20, tzinfo=timezone.utc)

    def _ans(elder, text):
        return ElderAnswer(elder=elder, text=text, error=None, agreed=None, created_at=t)

    return Round(
        number=1,
        turns=[
            Turn(elder="ada", answer=_ans("ada", "Ada R1")),
            Turn(elder="kai", answer=_ans("kai", "Kai R1")),
            Turn(elder="mei", answer=_ans("mei", "Mei R1")),
        ],
    )


class TestUserMessage:
    def test_r1_prompt_matches_default(self):
        rules = SilentReviseRules()
        msg = rules.user_message(_debate("Should I ship?"), "ada", 1)
        assert "Should I ship?" in msg

    def test_r2_prompt_is_silent_revise(self):
        rules = SilentReviseRules()
        d = _debate()
        d.rounds.append(_r1())
        msg = rules.user_message(d, "ada", 2)
        low = msg.lower()
        # Must NOT ask for peer questions or convergence.
        assert "questions:" not in low or "do not include" in low
        assert "converged" not in low or "do not include" in low
        assert "do not address them" in low or "private revision" in low
        assert "re-write" in low or "revised answer" in low
        # Must contain the other advisors' R1s for context.
        assert "Kai R1" in msg
        assert "Mei R1" in msg

    def test_r3_raises(self):
        rules = SilentReviseRules()
        d = _debate()
        d.rounds.append(_r1())
        try:
            rules.user_message(d, "ada", 3)
        except ValueError as e:
            assert "two rounds" in str(e).lower()
        else:
            raise AssertionError("expected ValueError for round 3 under SilentReviseRules")


class TestValidate:
    def _validate(self, **kwargs):
        rules = SilentReviseRules()
        return rules.validate(
            agreed=kwargs.get("agreed"),
            questions=kwargs.get("questions", ()),
            round_num=kwargs.get("round_num", 2),
            from_elder=kwargs.get("from_elder", "ada"),
        )

    def test_accepts_substantive_answer(self):
        assert isinstance(self._validate(), ValidationOk)

    def test_rejects_converged_yes(self):
        result = self._validate(agreed=True)
        assert isinstance(result, Violation)
        assert "convergence" in result.reason.lower()

    def test_rejects_converged_no(self):
        result = self._validate(agreed=False)
        assert isinstance(result, Violation)

    def test_rejects_peer_question(self):
        q = ElderQuestion(from_elder="ada", to_elder="kai", text="why?", round_number=2)
        result = self._validate(questions=(q,))
        assert isinstance(result, Violation)
        assert "questions" in result.reason.lower()

    def test_same_contract_for_r1_and_r2(self):
        # Silent-revise imposes the same contract on both rounds.
        r1 = self._validate(round_num=1)
        r2 = self._validate(round_num=2)
        assert isinstance(r1, ValidationOk) and isinstance(r2, ValidationOk)


class TestIsConverged:
    def test_never_converged(self):
        rules = SilentReviseRules()
        r = Round(number=2, turns=[])
        assert rules.is_converged(r) is False

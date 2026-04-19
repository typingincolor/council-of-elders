from datetime import datetime, timezone

from council.domain.debate_analytics import (
    analyse_latching,
    analyse_low_delta_rounds,
)
from council.domain.models import (
    CouncilPack,
    Debate,
    ElderAnswer,
    ElderQuestion,
    Round,
    Turn,
)


def _ans(elder, text="x", agreed=None):
    return ElderAnswer(
        elder=elder,
        text=text,
        error=None,
        agreed=agreed,
        created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
    )


def _debate(rounds):
    return Debate(
        id="t",
        prompt="Q?",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=rounds,
        status="in_progress",
        synthesis=None,
    )


class TestLatching:
    def test_substantive_reaffirm_is_substantive(self):
        # Claude converges R3, Gemini asks Claude a question in R3.
        # Claude's R4 body is long → substantive re-engagement.
        q = ElderQuestion(from_elder="gemini", to_elder="claude", text="Why X?", round_number=3)
        r3 = Round(
            number=3,
            turns=[
                Turn(
                    elder="claude",
                    answer=_ans("claude", "Detailed R3 answer.", agreed=True),
                ),
                Turn(elder="gemini", answer=_ans("gemini", "g3", agreed=False), questions=(q,)),
                Turn(elder="chatgpt", answer=_ans("chatgpt", "x3", agreed=True)),
            ],
        )
        r4 = Round(
            number=4,
            turns=[
                Turn(
                    elder="claude",
                    answer=_ans("claude", "A" * 500, agreed=True),  # long body
                ),
                Turn(elder="gemini", answer=_ans("gemini", "g4", agreed=True)),
                Turn(elder="chatgpt", answer=_ans("chatgpt", "x4", agreed=True)),
            ],
        )
        report = analyse_latching(_debate([r3, r4]))
        assert report.n == 1
        assert report.observations[0].classification == "substantive"
        assert report.observations[0].elder == "claude"
        assert report.observations[0].peer_asker == "gemini"

    def test_disengaged_reaffirm_is_disengaged(self):
        q = ElderQuestion(from_elder="gemini", to_elder="claude", text="Why?", round_number=3)
        r3 = Round(
            number=3,
            turns=[
                Turn(elder="claude", answer=_ans("claude", "c3", agreed=True)),
                Turn(elder="gemini", answer=_ans("gemini", "g3", agreed=False), questions=(q,)),
                Turn(elder="chatgpt", answer=_ans("chatgpt", "x3", agreed=True)),
            ],
        )
        r4 = Round(
            number=4,
            turns=[
                Turn(elder="claude", answer=_ans("claude", "Yes.", agreed=True)),  # tiny
                Turn(elder="gemini", answer=_ans("gemini", "g4", agreed=True)),
                Turn(elder="chatgpt", answer=_ans("chatgpt", "x4", agreed=True)),
            ],
        )
        report = analyse_latching(_debate([r3, r4]))
        assert report.observations[0].classification == "disengaged_reaffirm"
        assert report.disengaged_rate == 1.0

    def test_flip_is_flip(self):
        q = ElderQuestion(from_elder="gemini", to_elder="claude", text="Why?", round_number=3)
        r3 = Round(
            number=3,
            turns=[
                Turn(elder="claude", answer=_ans("claude", "c3", agreed=True)),
                Turn(elder="gemini", answer=_ans("gemini", "g3", agreed=False), questions=(q,)),
                Turn(elder="chatgpt", answer=_ans("chatgpt", "x3", agreed=True)),
            ],
        )
        r4 = Round(
            number=4,
            turns=[
                # Claude flipped to CONVERGED: no.
                Turn(elder="claude", answer=_ans("claude", "A" * 500, agreed=False)),
                Turn(elder="gemini", answer=_ans("gemini", "g4", agreed=True)),
                Turn(elder="chatgpt", answer=_ans("chatgpt", "x4", agreed=True)),
            ],
        )
        report = analyse_latching(_debate([r3, r4]))
        assert report.observations[0].classification == "flip"
        assert report.flip_rate == 1.0

    def test_no_peer_question_produces_no_observation(self):
        # Claude converges R3 but no peer asked it anything.
        r3 = Round(
            number=3,
            turns=[
                Turn(elder="claude", answer=_ans("claude", "c3", agreed=True)),
                Turn(elder="gemini", answer=_ans("gemini", "g3", agreed=True)),
                Turn(elder="chatgpt", answer=_ans("chatgpt", "x3", agreed=True)),
            ],
        )
        r4 = Round(
            number=4,
            turns=[
                Turn(elder="claude", answer=_ans("claude", "c4", agreed=True)),
                Turn(elder="gemini", answer=_ans("gemini", "g4", agreed=True)),
                Turn(elder="chatgpt", answer=_ans("chatgpt", "x4", agreed=True)),
            ],
        )
        report = analyse_latching(_debate([r3, r4]))
        assert report.n == 0


class TestLowDelta:
    def test_near_paraphrase_detected(self):
        # An elder repeats almost the same text in two consecutive rounds.
        base = "My position is that we should ship features incrementally " * 5
        r2 = Round(
            number=2,
            turns=[
                Turn(elder="claude", answer=_ans("claude", base)),
                Turn(elder="gemini", answer=_ans("gemini", "g2")),
                Turn(elder="chatgpt", answer=_ans("chatgpt", "x2")),
            ],
        )
        r3 = Round(
            number=3,
            turns=[
                Turn(
                    elder="claude",
                    # Tiny edit — high similarity.
                    answer=_ans("claude", base + " Also: tests."),
                ),
                Turn(elder="gemini", answer=_ans("gemini", "g3")),
                Turn(elder="chatgpt", answer=_ans("chatgpt", "x3")),
            ],
        )
        report = analyse_low_delta_rounds(_debate([r2, r3]))
        claude_delta = next(d for d in report.deltas if d.elder == "claude")
        assert claude_delta.is_low_delta is True
        assert claude_delta.similarity > 0.92

    def test_substantive_change_not_flagged(self):
        r2 = Round(
            number=2,
            turns=[
                Turn(elder="claude", answer=_ans("claude", "Ship incrementally.")),
                Turn(elder="gemini", answer=_ans("gemini", "g2")),
                Turn(elder="chatgpt", answer=_ans("chatgpt", "x2")),
            ],
        )
        r3 = Round(
            number=3,
            turns=[
                Turn(
                    elder="claude",
                    answer=_ans(
                        "claude",
                        "I changed my mind: the correct approach is a bounded rewrite "
                        "because shared-surface migration costs are lower than incremental refactor.",
                    ),
                ),
                Turn(elder="gemini", answer=_ans("gemini", "g3")),
                Turn(elder="chatgpt", answer=_ans("chatgpt", "x3")),
            ],
        )
        report = analyse_low_delta_rounds(_debate([r2, r3]))
        claude_delta = next(d for d in report.deltas if d.elder == "claude")
        assert claude_delta.is_low_delta is False

    def test_skips_r1(self):
        r1 = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_ans("claude", "c1")),
                Turn(elder="gemini", answer=_ans("gemini", "g1")),
                Turn(elder="chatgpt", answer=_ans("chatgpt", "x1")),
            ],
        )
        report = analyse_low_delta_rounds(_debate([r1]))
        assert report.n == 0

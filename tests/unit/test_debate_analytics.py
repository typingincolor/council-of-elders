from datetime import datetime, timezone


from council.domain.debate_analytics import (
    _parse_drift_verdict,
    analyse_drift,
    analyse_latching,
    analyse_low_delta_rounds,
)
from council.domain.models import (
    CouncilPack,
    Debate,
    ElderAnswer,
    ElderQuestion,
    Message,
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


class TestDriftParse:
    def test_parses_clean_reply(self):
        raw = (
            "shape_fit: 3\n"
            "content_fit: 3\n"
            "drift_flag: no\n"
            "reason: The synthesis is a one-sentence headline matching the user's ask."
        )
        obs = _parse_drift_verdict(raw, "abc")
        assert obs.debate_id == "abc"
        assert obs.shape_fit == 3
        assert obs.content_fit == 3
        assert obs.drift_flag is False
        assert "headline" in obs.reason

    def test_parses_drift_case(self):
        raw = (
            "shape_fit: 1\n"
            "content_fit: 2\n"
            "drift_flag: yes\n"
            "reason: User asked for a headline; synthesis is a 30-word mission statement."
        )
        obs = _parse_drift_verdict(raw, "xyz")
        assert obs.shape_fit == 1
        assert obs.content_fit == 2
        assert obs.drift_flag is True

    def test_tolerates_markdown_fencing(self):
        raw = (
            "```\n"
            "shape_fit: 2\n"
            "content_fit: 3\n"
            "drift_flag: no\n"
            "reason: Minor shape gap but content is accurate.\n"
            "```"
        )
        obs = _parse_drift_verdict(raw, "d")
        assert obs.shape_fit == 2
        assert obs.drift_flag is False

    def test_tolerates_case_variants(self):
        raw = "Shape_Fit: 3\nCONTENT_FIT: 2\nDrift_Flag: NO\nReason: OK."
        obs = _parse_drift_verdict(raw, "d")
        assert obs.shape_fit == 3
        assert obs.content_fit == 2
        assert obs.drift_flag is False

    def test_defaults_on_missing_fields(self):
        # Model emitted nonsense — defaults to neutral reading, NOT a
        # false-positive drift flag.
        obs = _parse_drift_verdict("I don't know what to say.", "d")
        assert obs.shape_fit == 2
        assert obs.content_fit == 2
        assert obs.drift_flag is False
        assert "did not include" in obs.reason

    def test_raw_field_preserved(self):
        raw = "shape_fit: 0\ncontent_fit: 0\ndrift_flag: yes\nreason: x"
        obs = _parse_drift_verdict(raw, "d")
        assert obs.raw == raw


class _StubJudge:
    """Minimal stand-in for an ElderPort; returns a pre-scripted reply."""

    elder_id = "claude"

    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.last_conversation: list[Message] | None = None

    async def ask(self, conversation, *, timeout_s: float = 45.0) -> str:
        self.last_conversation = list(conversation)
        return self._reply

    async def health_check(self) -> bool:
        return True


class TestAnalyseDrift:
    async def test_returns_none_when_no_synthesis(self):
        # A debate without synthesis cannot be judged.
        r1 = Round(
            number=1,
            turns=[Turn(elder="claude", answer=_ans("claude", "x"))],
        )
        d = _debate([r1])
        # synthesis is None in this _debate() helper
        judge = _StubJudge("shape_fit: 3\ncontent_fit: 3\ndrift_flag: no\nreason: fine")
        result = await analyse_drift(d, judge)
        assert result is None

    async def test_calls_judge_with_prompt_containing_question_and_synthesis(self):
        r1 = Round(
            number=1,
            turns=[Turn(elder="claude", answer=_ans("claude", "initial take"))],
        )
        d = Debate(
            id="abc",
            prompt="Give me a one-sentence headline.",
            pack=CouncilPack(name="bare", shared_context=None, personas={}),
            rounds=[r1],
            status="synthesized",
            synthesis=_ans("claude", "Ship faster."),
        )
        judge = _StubJudge("shape_fit: 3\ncontent_fit: 3\ndrift_flag: no\nreason: clean headline")
        result = await analyse_drift(d, judge)
        assert result is not None
        assert result.debate_id == "abc"
        assert result.drift_flag is False
        # Confirm the prompt sent to the judge contains both pieces.
        assert judge.last_conversation is not None
        judge_prompt = judge.last_conversation[0].content
        assert "Give me a one-sentence headline." in judge_prompt
        assert "Ship faster." in judge_prompt

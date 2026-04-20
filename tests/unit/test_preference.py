import random


from council.adapters.elders.fake import FakeElder
from council.domain.preference import (
    JudgeVerdict,
    MultiJudgeVerdict,
    PreferenceVerdict,
    _aggregate_winners,
    judge_preference,
    judge_preference_multi,
)


# Empirically derived seeds for deterministic X/Y slot assignment.
# The judge_preference function calls rng.random() once; values < 0.5 put
# synthesis into X, values >= 0.5 put best_r1 into X.
# Seed 1 → 0.13  → X=synthesis.
# Seed 0 → 0.84  → X=best_r1.
_SEED_X_IS_SYNTHESIS = 1
_SEED_X_IS_BEST_R1 = 0


class TestJudgePreference:
    async def test_synthesis_wins_when_x_was_synthesis_and_winner_x(self):
        judge = FakeElder(elder_id="ada", replies=["winner: X\nreason: synth tighter.\n"])
        v = await judge_preference(
            question="Q?",
            synthesis="S",
            best_r1="B",
            judge_port=judge,
            rng=random.Random(_SEED_X_IS_SYNTHESIS),
        )
        assert isinstance(v, PreferenceVerdict)
        assert v.winner == "synthesis"
        assert "synth tighter" in v.reason

    async def test_best_r1_wins_when_x_was_synthesis_and_winner_y(self):
        judge = FakeElder(elder_id="ada", replies=["winner: Y\nreason: R1 clearer.\n"])
        v = await judge_preference(
            question="Q?",
            synthesis="S",
            best_r1="B",
            judge_port=judge,
            rng=random.Random(_SEED_X_IS_SYNTHESIS),
        )
        assert v.winner == "best_r1"

    async def test_best_r1_wins_when_x_was_best_r1_and_winner_x(self):
        judge = FakeElder(elder_id="ada", replies=["winner: X\nreason: x slot tighter.\n"])
        v = await judge_preference(
            question="Q?",
            synthesis="S",
            best_r1="B",
            judge_port=judge,
            rng=random.Random(_SEED_X_IS_BEST_R1),
        )
        assert v.winner == "best_r1"

    async def test_synthesis_wins_when_x_was_best_r1_and_winner_y(self):
        judge = FakeElder(elder_id="ada", replies=["winner: Y\nreason: y slot tighter.\n"])
        v = await judge_preference(
            question="Q?",
            synthesis="S",
            best_r1="B",
            judge_port=judge,
            rng=random.Random(_SEED_X_IS_BEST_R1),
        )
        assert v.winner == "synthesis"

    async def test_tie_preserved(self):
        judge = FakeElder(elder_id="ada", replies=["winner: TIE\nreason: both ok.\n"])
        v = await judge_preference(
            question="Q?",
            synthesis="S",
            best_r1="B",
            judge_port=judge,
            rng=random.Random(0),
        )
        assert v.winner == "tie"

    async def test_unparseable_reply_defaults_to_tie(self):
        judge = FakeElder(elder_id="ada", replies=["banana\n"])
        v = await judge_preference(
            question="Q?",
            synthesis="S",
            best_r1="B",
            judge_port=judge,
            rng=random.Random(0),
        )
        assert v.winner == "tie"
        assert v.reason == ""

    async def test_tolerates_markdown_fence(self):
        judge = FakeElder(
            elder_id="ada",
            replies=["```\nwinner: X\nreason: synth better.\n```"],
        )
        v = await judge_preference(
            question="Q?",
            synthesis="S",
            best_r1="B",
            judge_port=judge,
            rng=random.Random(_SEED_X_IS_SYNTHESIS),
        )
        assert v.winner == "synthesis"


def _jv(model: str, winner: str) -> JudgeVerdict:
    return JudgeVerdict(
        judge_model=model,
        verdict=PreferenceVerdict(winner=winner, reason="", raw=""),  # type: ignore[arg-type]
    )


class TestAggregateWinners:
    def test_empty_is_tie_and_unanimous(self):
        agg, unan = _aggregate_winners(())
        assert agg == "tie" and unan is True

    def test_all_agree_synthesis(self):
        agg, unan = _aggregate_winners((_jv("a", "synthesis"), _jv("b", "synthesis")))
        assert agg == "synthesis" and unan is True

    def test_split_vote_becomes_tie(self):
        agg, unan = _aggregate_winners((_jv("a", "synthesis"), _jv("b", "best_r1")))
        assert agg == "tie" and unan is False

    def test_majority_wins_over_minority(self):
        agg, unan = _aggregate_winners(
            (_jv("a", "synthesis"), _jv("b", "synthesis"), _jv("c", "best_r1"))
        )
        assert agg == "synthesis" and unan is False

    def test_tie_verdict_counts_as_its_own_category(self):
        # All three judges emit "tie" → aggregate is tie, unanimous.
        agg, unan = _aggregate_winners((_jv("a", "tie"), _jv("b", "tie"), _jv("c", "tie")))
        assert agg == "tie" and unan is True


class TestJudgePreferenceMulti:
    """Integration tests that account for the shared RNG advancing
    between judges: judge[0] sees one X/Y slot flip, judge[1] sees the
    next. Each judge's rubric reply has to be written relative to the
    slot it sees.
    """

    # With seed 1, the two consecutive rng.random() calls are:
    #   call 1: 0.134 → X = synthesis  (judge[0] slot layout)
    #   call 2: 0.847 → X = best_r1    (judge[1] slot layout)
    _SEED_FLIPPED_SLOTS = 1

    async def test_two_judges_unanimous_synthesis(self):
        # Judge 0 sees X=synthesis; reply "winner: X" → synthesis.
        # Judge 1 sees X=best_r1;   reply "winner: Y" → synthesis.
        judges = [
            (
                "google/gemini-2.5-flash",
                FakeElder(
                    elder_id="ada",
                    replies=["winner: X\nreason: synth a.\n"],
                ),
            ),
            (
                "anthropic/claude-haiku-4.5",
                FakeElder(
                    elder_id="ada",
                    replies=["winner: Y\nreason: synth b.\n"],
                ),
            ),
        ]
        result = await judge_preference_multi(
            question="Q?",
            synthesis="S",
            best_r1="B",
            judges=judges,
            rng=random.Random(self._SEED_FLIPPED_SLOTS),
        )
        assert isinstance(result, MultiJudgeVerdict)
        assert result.aggregate == "synthesis"
        assert result.unanimous is True
        assert len(result.verdicts) == 2
        assert result.verdicts[0].judge_model == "google/gemini-2.5-flash"
        assert result.verdicts[1].judge_model == "anthropic/claude-haiku-4.5"

    async def test_two_judges_split_aggregates_to_tie(self):
        # Judge 0 sees X=synthesis; reply "winner: X" → synthesis.
        # Judge 1 sees X=best_r1;   reply "winner: X" → best_r1.
        judges = [
            (
                "google/gemini-2.5-flash",
                FakeElder(
                    elder_id="ada",
                    replies=["winner: X\nreason: synth.\n"],
                ),
            ),
            (
                "anthropic/claude-haiku-4.5",
                FakeElder(
                    elder_id="ada",
                    replies=["winner: X\nreason: r1.\n"],
                ),
            ),
        ]
        result = await judge_preference_multi(
            question="Q?",
            synthesis="S",
            best_r1="B",
            judges=judges,
            rng=random.Random(self._SEED_FLIPPED_SLOTS),
        )
        assert result.aggregate == "tie"
        assert result.unanimous is False

    async def test_empty_judge_list_returns_vacuously_unanimous_tie(self):
        result = await judge_preference_multi(
            question="Q?",
            synthesis="S",
            best_r1="B",
            judges=[],
        )
        assert result.aggregate == "tie"
        assert result.unanimous is True
        assert result.verdicts == ()

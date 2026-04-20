import random


from council.adapters.elders.fake import FakeElder
from council.domain.preference import PreferenceVerdict, judge_preference


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

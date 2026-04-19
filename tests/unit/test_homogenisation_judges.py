from council.experiments.homogenisation.judges import (
    BestR1Observation,
    JaccardObservation,
    _parse_best_r1,
    _parse_claim_overlap,
)


class TestParseClaimOverlap:
    def test_well_formed_response_parses(self) -> None:
        raw = (
            "shared_count: 3\n"
            "a_only_count: 1\n"
            "b_only_count: 2\n"
            "note: Both agreed on core recommendation.\n"
        )
        obs = _parse_claim_overlap(raw)
        assert obs == JaccardObservation(
            shared=3, a_only=1, b_only=2,
            note="Both agreed on core recommendation.", raw=raw,
        )

    def test_jaccard_property(self) -> None:
        obs = JaccardObservation(shared=3, a_only=1, b_only=2, note="", raw="")
        assert obs.jaccard == 0.5  # 3/6

    def test_jaccard_is_zero_when_all_counts_are_zero(self) -> None:
        obs = JaccardObservation(shared=0, a_only=0, b_only=0, note="", raw="")
        assert obs.jaccard == 0.0

    def test_case_insensitive_keys(self) -> None:
        raw = "SHARED_COUNT: 5\nA_ONLY_COUNT: 0\nB_ONLY_COUNT: 0\nNote: n/a\n"
        obs = _parse_claim_overlap(raw)
        assert obs.shared == 5 and obs.a_only == 0 and obs.b_only == 0

    def test_missing_counts_default_to_zero(self) -> None:
        raw = "note: judge did not emit counts\n"
        obs = _parse_claim_overlap(raw)
        assert obs.shared == 0 and obs.a_only == 0 and obs.b_only == 0

    def test_markdown_fence_stripped(self) -> None:
        raw = "```\nshared_count: 2\na_only_count: 1\nb_only_count: 1\nnote: ok\n```\n"
        obs = _parse_claim_overlap(raw)
        assert obs.shared == 2


class TestParseBestR1:
    def test_well_formed_response_parses(self) -> None:
        raw = "best: 2\nreason: Answer 2 cites concrete tradeoffs.\n"
        obs = _parse_best_r1(raw)
        assert obs == BestR1Observation(
            best_index=2, reason="Answer 2 cites concrete tradeoffs.", raw=raw,
        )

    def test_default_on_unparsable(self) -> None:
        obs = _parse_best_r1("gibberish")
        assert obs.best_index == 1  # documented safe default
        assert obs.reason == ""

    def test_rejects_out_of_range(self) -> None:
        obs = _parse_best_r1("best: 7\nreason: invalid\n")
        assert obs.best_index == 1  # out-of-range falls back to default

    def test_case_insensitive_key(self) -> None:
        obs = _parse_best_r1("BEST: 3\nREASON: all clear\n")
        assert obs.best_index == 3


import random

from council.experiments.homogenisation.judges import (
    PreferenceObservation,
    _parse_preference,
    _resolve_preference_winner,
    _shuffle_xy,
)


class TestShuffleXY:
    def test_reproducible_with_same_seed(self) -> None:
        rng_a = random.Random(42)
        rng_b = random.Random(42)
        x1, y1, x_was1 = _shuffle_xy("S", "R", rng_a)
        x2, y2, x_was2 = _shuffle_xy("S", "R", rng_b)
        assert (x1, y1, x_was1) == (x2, y2, x_was2)

    def test_shuffle_either_assigns_synthesis_to_x_or_y(self) -> None:
        # Over many trials we should see both assignments.
        seen: set[str] = set()
        for seed in range(20):
            _, _, x_was = _shuffle_xy("synth", "best", random.Random(seed))
            seen.add(x_was)
            if seen == {"synthesis", "best_r1"}:
                break
        assert seen == {"synthesis", "best_r1"}


class TestParsePreference:
    def test_winner_x_when_synthesis_is_x(self) -> None:
        raw = "winner: X\nreason: more direct.\n"
        obs = _parse_preference(raw, x_was="synthesis")
        assert obs.winner == "synthesis"
        assert obs.x_was == "synthesis"

    def test_winner_y_when_synthesis_is_x(self) -> None:
        raw = "winner: Y\nreason: better facts.\n"
        obs = _parse_preference(raw, x_was="synthesis")
        assert obs.winner == "best_r1"

    def test_winner_y_when_synthesis_is_y(self) -> None:
        raw = "winner: Y\nreason: clearer.\n"
        obs = _parse_preference(raw, x_was="best_r1")
        assert obs.winner == "synthesis"

    def test_tie(self) -> None:
        obs = _parse_preference("winner: TIE\nreason: equivalent.\n", x_was="synthesis")
        assert obs.winner == "tie"

    def test_unparsable_defaults_to_tie(self) -> None:
        obs = _parse_preference("blah blah", x_was="synthesis")
        assert obs.winner == "tie"


def test_resolve_preference_winner_handles_all_cases() -> None:
    assert _resolve_preference_winner("X", "synthesis") == "synthesis"
    assert _resolve_preference_winner("Y", "synthesis") == "best_r1"
    assert _resolve_preference_winner("X", "best_r1") == "best_r1"
    assert _resolve_preference_winner("Y", "best_r1") == "synthesis"
    assert _resolve_preference_winner("TIE", "synthesis") == "tie"

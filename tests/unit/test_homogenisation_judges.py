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

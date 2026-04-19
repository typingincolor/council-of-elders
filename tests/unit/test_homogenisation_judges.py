from council.experiments.homogenisation.judges import (
    JaccardObservation,
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

from __future__ import annotations

import math


from council.experiments.homogenisation.scorer import (
    _binomial_ci_90,
    _summarise_rosters,
)


def test_binomial_ci_90_returns_symmetric_tight_interval_for_5050() -> None:
    lo, hi = _binomial_ci_90(successes=5, n=10)
    assert 0.2 <= lo <= 0.45
    assert 0.55 <= hi <= 0.8
    assert math.isclose((lo + hi) / 2, 0.5, abs_tol=0.05)


def test_binomial_ci_90_handles_zero_n() -> None:
    lo, hi = _binomial_ci_90(successes=0, n=0)
    assert lo == 0.0 and hi == 1.0


def test_summarise_rosters_computes_mean_median_rate() -> None:
    rows = [
        {"roster": "r1", "r1_jaccard": 0.4, "preference_winner": "synthesis"},
        {"roster": "r1", "r1_jaccard": 0.6, "preference_winner": "best_r1"},
        {"roster": "r1", "r1_jaccard": 0.8, "preference_winner": "tie"},
        {"roster": "r2", "r1_jaccard": 0.1, "preference_winner": "synthesis"},
    ]
    summaries = _summarise_rosters(rows)
    by_name = {s.roster: s for s in summaries}
    assert by_name["r1"].n_debates == 3
    assert math.isclose(by_name["r1"].mean_r1_jaccard, 0.6, abs_tol=1e-9)
    assert math.isclose(by_name["r1"].median_r1_jaccard, 0.6, abs_tol=1e-9)
    # 1 synth + 1 tie (=0.5) + 0 = 1.5 / 3
    assert math.isclose(by_name["r1"].preference_rate, 0.5, abs_tol=1e-9)
    assert by_name["r2"].preference_rate == 1.0

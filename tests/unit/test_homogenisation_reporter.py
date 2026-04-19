from __future__ import annotations

import json
from pathlib import Path

from council.experiments.homogenisation.corpus import CorpusPrompt
from council.experiments.homogenisation.reporter import render_report
from council.experiments.homogenisation.rosters import RosterSpec


def _fixture_scores() -> dict[str, object]:
    return {
        "rows": [
            {"debate_id": "d1", "roster": "homogeneous", "prompt_id": "p1",
             "r1_jaccard": 0.8, "preference_winner": "synthesis"},
            {"debate_id": "d2", "roster": "mixed_baseline", "prompt_id": "p1",
             "r1_jaccard": 0.4, "preference_winner": "best_r1"},
        ],
        "summaries": [
            {"roster": "homogeneous", "n_debates": 1, "mean_r1_jaccard": 0.8,
             "median_r1_jaccard": 0.8, "preference_rate": 1.0,
             "preference_ci_lo": 0.0, "preference_ci_hi": 1.0},
            {"roster": "mixed_baseline", "n_debates": 1, "mean_r1_jaccard": 0.4,
             "median_r1_jaccard": 0.4, "preference_rate": 0.0,
             "preference_ci_lo": 0.0, "preference_ci_hi": 1.0},
        ],
    }


def test_render_report_contains_all_key_sections(tmp_path: Path) -> None:
    scores_path = tmp_path / "scores.json"
    scores_path.write_text(json.dumps(_fixture_scores()))
    corpus = [CorpusPrompt(id="p1", shape="headline", prompt="Q?")]
    rosters = (
        RosterSpec(name="homogeneous", models={"claude": "m1", "gemini": "m1", "chatgpt": "m1"}),
        RosterSpec(name="mixed_baseline", models={"claude": "m2", "gemini": "m3", "chatgpt": "m4"}),
    )
    md = render_report(
        scores_path=scores_path, corpus=corpus, rosters=rosters, run_id="2026-04-19-test",
    )
    for section in [
        "# Model homogenisation probe",
        "## Question",
        "## Rosters tested",
        "## Corpus",
        "### Metric 1",
        "### Metric 2",
        "## Interpretation",
        "## Caveats",
        "## Appendix",
    ]:
        assert section in md, f"missing section: {section!r}"


def test_render_report_interprets_small_diversity_gap() -> None:
    scores_path_input = _fixture_scores()
    # Shrink the gap: homogeneous 0.60, mixed 0.58 → diversity negligible.
    scores_path_input["summaries"][0]["mean_r1_jaccard"] = 0.60
    scores_path_input["summaries"][1]["mean_r1_jaccard"] = 0.58
    from pathlib import Path as _P
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as td:
        p = _P(td) / "scores.json"
        p.write_text(json.dumps(scores_path_input))
        corpus = [CorpusPrompt(id="p1", shape="headline", prompt="Q?")]
        rosters = (
            RosterSpec(name="homogeneous", models={"claude": "m1", "gemini": "m1", "chatgpt": "m1"}),
            RosterSpec(name="mixed_baseline", models={"claude": "m2", "gemini": "m3", "chatgpt": "m4"}),
        )
        md = render_report(
            scores_path=p, corpus=corpus, rosters=rosters, run_id="2026-04-19-test",
        )
    assert "negligible" in md.lower() or "doesn't matter" in md.lower()


def test_render_report_flags_unexpected_negative_preference_gap(tmp_path: Path) -> None:
    """When mixed_baseline.preference_rate is >0.10 below homogeneous, the
    interpretation must flag it rather than silently emit no bullet."""
    fixture = _fixture_scores()
    # homogeneous=1.0, mixed=0.0 → pref_gap = mix - hom = -1.0
    fixture["summaries"][0]["preference_rate"] = 1.0
    fixture["summaries"][1]["preference_rate"] = 0.0
    scores_path = tmp_path / "scores.json"
    scores_path.write_text(json.dumps(fixture))
    corpus = [CorpusPrompt(id="p1", shape="headline", prompt="Q?")]
    rosters = (
        RosterSpec(name="homogeneous", models={"claude": "m1", "gemini": "m1", "chatgpt": "m1"}),
        RosterSpec(name="mixed_baseline", models={"claude": "m2", "gemini": "m3", "chatgpt": "m4"}),
    )
    md = render_report(
        scores_path=scores_path, corpus=corpus, rosters=rosters, run_id="2026-04-19-test",
    )
    assert "unexpected" in md.lower()

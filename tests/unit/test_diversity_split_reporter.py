import json
from pathlib import Path

from council.experiments.diversity_split.conditions import CONDITIONS
from council.experiments.diversity_split.reporter import render_report
from council.experiments.homogenisation.corpus import CorpusPrompt


def _summaries_for_each_cell(
    *,
    a_jaccard: float = 0.5,
    a_pref: float = 0.3,
    b_jaccard: float = 0.45,
    b_pref: float = 0.35,
    c_jaccard: float = 0.3,
    c_pref: float = 0.6,
    d_jaccard: float = 0.28,
    d_pref: float = 0.7,
) -> list[dict]:
    def _row(name, j, p):
        return {
            "roster": name,
            "n_debates": 8,
            "mean_r1_jaccard": j,
            "median_r1_jaccard": j,
            "preference_rate": p,
            "preference_ci_lo": max(0.0, p - 0.2),
            "preference_ci_hi": min(1.0, p + 0.2),
        }

    return [
        _row("same_model_same_role", a_jaccard, a_pref),
        _row("same_model_diff_role", b_jaccard, b_pref),
        _row("diff_model_same_role", c_jaccard, c_pref),
        _row("diff_model_diff_role", d_jaccard, d_pref),
    ]


def _scores_file(tmp_path: Path, summaries: list[dict], rows=None) -> Path:
    data = {"rows": rows or [], "summaries": summaries}
    path = tmp_path / "scores.json"
    path.write_text(json.dumps(data))
    return path


class TestRenderReport:
    def test_includes_all_four_conditions(self, tmp_path: Path):
        path = _scores_file(tmp_path, _summaries_for_each_cell())
        md = render_report(
            scores_path=path,
            corpus=[CorpusPrompt(id="p1", shape="strategy", prompt="Q?")],
            conditions=CONDITIONS,
            run_id="t",
        )
        for name in (
            "same_model_same_role",
            "same_model_diff_role",
            "diff_model_same_role",
            "diff_model_diff_role",
        ):
            assert name in md

    def test_renders_2x2_table_shape(self, tmp_path: Path):
        path = _scores_file(tmp_path, _summaries_for_each_cell())
        md = render_report(
            scores_path=path,
            corpus=[CorpusPrompt(id="p1", shape="strategy", prompt="Q?")],
            conditions=CONDITIONS,
            run_id="t",
        )
        assert "| | same role | different role |" in md
        assert "**same model**" in md
        assert "**different model**" in md

    def test_interpret_fires_compose_bullet_when_d_above_c(self, tmp_path: Path):
        path = _scores_file(
            tmp_path,
            _summaries_for_each_cell(c_pref=0.55, d_pref=0.75),
        )
        md = render_report(
            scores_path=path,
            corpus=[CorpusPrompt(id="p1", shape="strategy", prompt="Q?")],
            conditions=CONDITIONS,
            run_id="t",
        )
        assert "two axes compose" in md.lower() or "d−c" in md.lower()

    def test_interpret_flags_role_substitution_when_b_close_to_c(self, tmp_path: Path):
        # Personas substituting for model diversity: B ~ C.
        path = _scores_file(
            tmp_path,
            _summaries_for_each_cell(b_pref=0.55, c_pref=0.60),
        )
        md = render_report(
            scores_path=path,
            corpus=[CorpusPrompt(id="p1", shape="strategy", prompt="Q?")],
            conditions=CONDITIONS,
            run_id="t",
        )
        # Gap C−B ≤ 0.10 → "comparable gains" verdict.
        assert "comparable gains" in md.lower()

    def test_interpret_flags_model_diversity_when_c_clearly_above_b(self, tmp_path: Path):
        path = _scores_file(
            tmp_path,
            _summaries_for_each_cell(b_pref=0.35, c_pref=0.65),
        )
        md = render_report(
            scores_path=path,
            corpus=[CorpusPrompt(id="p1", shape="strategy", prompt="Q?")],
            conditions=CONDITIONS,
            run_id="t",
        )
        assert "personas are not substitutes" in md.lower()

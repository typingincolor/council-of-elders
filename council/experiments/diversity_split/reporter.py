"""Report renderer for the diversity_split experiment.

Renders a 2×2 table of (same/diff model) × (same/diff role) with mean
R1 Jaccard and synthesis-vs-best-R1 preference rate per cell, plus a
narrative reading the four cells together.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

from council.experiments.diversity_split.conditions import Condition
from council.experiments.homogenisation.corpus import CorpusPrompt

_CELL_LABELS: dict[str, tuple[str, str]] = {
    # condition name → (model-axis label, role-axis label)
    "same_model_same_role": ("same model", "same role"),
    "same_model_diff_role": ("same model", "different role"),
    "diff_model_same_role": ("different model", "same role"),
    "diff_model_diff_role": ("different model", "different role"),
}


def _rosters_table(conditions: tuple[Condition, ...]) -> str:
    rows = [
        "| Condition | ada slot | kai slot | mei slot | pack |",
        "|---|---|---|---|---|",
    ]
    for c in conditions:
        rows.append(
            f"| `{c.name}` | `{c.roster.models['ada']}` | "
            f"`{c.roster.models['kai']}` | `{c.roster.models['mei']}` | "
            f"`{c.pack.name}` |"
        )
    return "\n".join(rows)


def _corpus_table(corpus: list[CorpusPrompt]) -> str:
    rows = ["| id | shape | prompt |", "|---|---|---|"]
    for p in corpus:
        rows.append(f"| `{p.id}` | {p.shape} | {p.prompt} |")
    return "\n".join(rows)


def _twoxtwo_jaccard(summaries: list[dict[str, Any]]) -> str:
    by_name = {s["roster"]: s for s in summaries}

    def cell(name: str, key: str) -> str:
        if name not in by_name:
            return "—"
        return f"{by_name[name][key]:.3f}"

    rows = [
        "| | same role | different role |",
        "|---|---|---|",
        f"| **same model** | {cell('same_model_same_role', 'mean_r1_jaccard')} | "
        f"{cell('same_model_diff_role', 'mean_r1_jaccard')} |",
        f"| **different model** | {cell('diff_model_same_role', 'mean_r1_jaccard')} | "
        f"{cell('diff_model_diff_role', 'mean_r1_jaccard')} |",
    ]
    return "\n".join(rows)


def _twoxtwo_preference(summaries: list[dict[str, Any]]) -> str:
    by_name = {s["roster"]: s for s in summaries}

    def cell(name: str) -> str:
        if name not in by_name:
            return "—"
        s = by_name[name]
        return (
            f"{s['preference_rate']:.3f} [{s['preference_ci_lo']:.3f}, {s['preference_ci_hi']:.3f}]"
        )

    rows = [
        "| | same role | different role |",
        "|---|---|---|",
        f"| **same model** | {cell('same_model_same_role')} | {cell('same_model_diff_role')} |",
        f"| **different model** | {cell('diff_model_same_role')} | "
        f"{cell('diff_model_diff_role')} |",
    ]
    return "\n".join(rows)


def _interpret(summaries: list[dict[str, Any]]) -> list[str]:
    """Compare the four cells on synthesis-vs-best-R1 preference.

    Stopping-criterion thresholds are pre-declared in the Stage 11 spec
    (``docs/superpowers/specs/2026-04-20-stage-11-diversity-split-design.md``):

    - Personas-substitute claim supported iff |C − B| ≤ 0.10.
    - Personas-don't-substitute claim supported iff C − B > 0.15.
    - Two-axes-compose claim supported iff D − C > 0.10.
    - Two-axes-don't-compose claim supported iff |D − C| ≤ 0.10.

    Intermediate zones (0.10 < |C − B| ≤ 0.15, for example) are reported
    as inconclusive rather than forced into a binary decision.
    """
    by = {s["roster"]: s for s in summaries}
    bullets: list[str] = []

    a = by.get("same_model_same_role", {}).get("preference_rate")
    b = by.get("same_model_diff_role", {}).get("preference_rate")
    c = by.get("diff_model_same_role", {}).get("preference_rate")
    d = by.get("diff_model_diff_role", {}).get("preference_rate")

    if a is not None and b is not None:
        gap = b - a
        if gap > 0.10:
            bullets.append(f"Role diversity alone moves the needle (B−A = {gap:+.3f}).")
        elif gap < -0.10:
            bullets.append(
                f"Role diversity alone HURT (B−A = {gap:+.3f}) — personas may be miscalibrated."
            )
        else:
            bullets.append(f"Role diversity alone is a wash (B−A = {gap:+.3f}; threshold ±0.10).")

    if a is not None and c is not None:
        gap = c - a
        if gap > 0.10:
            bullets.append(f"Model diversity alone moves the needle (C−A = {gap:+.3f}).")
        else:
            bullets.append(f"Model diversity alone not decisive here (C−A = {gap:+.3f}).")

    # Key B-vs-C decision: do personas substitute for model diversity?
    if b is not None and c is not None:
        gap = c - b
        if gap > 0.15:
            bullets.append(
                f"**Personas are NOT substitutes for model diversity** "
                f"(C−B = {gap:+.3f}, threshold >0.15). Drop the "
                f"persona-as-substitute pitch; personas become a flavour "
                f"layer, not the mechanism."
            )
        elif abs(gap) <= 0.10:
            bullets.append(
                f"**Personas substitute for model diversity** "
                f"(|C−B| = {abs(gap):.3f} ≤ 0.10). Positioning allows "
                f"'three copies of one cheap model + distinct personas' "
                f"as a valid configuration."
            )
        else:
            # 0.10 < |gap| ≤ 0.15: inconclusive zone.
            bullets.append(
                f"B-vs-C is in the inconclusive zone (C−B = {gap:+.3f}, "
                f"between ±0.10 and ±0.15). Expand to larger n before "
                f"drawing a conclusion on personas-as-substitute."
            )

    # D-vs-C decision: do the two axes compose?
    if d is not None and c is not None:
        gap = d - c
        if gap > 0.10:
            bullets.append(
                f"**The two axes compose** (D−C = {gap:+.3f} > 0.10). "
                f"Recommend combining model and persona diversity when "
                f"both are available."
            )
        elif abs(gap) <= 0.10:
            bullets.append(
                f"**Two axes do not compose** (|D−C| = {abs(gap):.3f} ≤ "
                f"0.10). Personas add no marginal value on top of model "
                f"diversity; drop the default persona pack."
            )
        else:
            bullets.append(
                f"Adding personas to diverse models HURT performance "
                f"(D−C = {gap:+.3f} < −0.10) — persona-model interaction "
                f"effect worth investigating."
            )

    return bullets


def render_report(
    *,
    scores_path: Path,
    corpus: list[CorpusPrompt],
    conditions: tuple[Condition, ...],
    run_id: str,
) -> str:
    data = json.loads(scores_path.read_text())
    rows: list[dict[str, Any]] = data["rows"]
    summaries: list[dict[str, Any]] = data["summaries"]
    date_str = _dt.date.today().isoformat()
    verdicts = _interpret(summaries)
    verdict_md = "\n".join(f"- {b}" for b in verdicts) or "- (no data)"

    appendix = "\n".join(
        [
            "| debate | condition | prompt | R1 Jaccard | winner |",
            "|---|---|---|---|---|",
            *(
                f"| `{r['debate_id'][:8]}` | {r['roster']} | {r['prompt_id']} | "
                f"{r['r1_jaccard']:.3f} | {r['preference_winner']} |"
                for r in rows
            ),
        ]
    )

    return f"""# Diversity-split 2×2 — {date_str}

Run id: `{run_id}`

## Question

Does value come from model diversity, from role (persona) diversity, or
both? Two axes, each at two levels, crossed.

## Conditions

{_rosters_table(conditions)}

## Corpus

{_corpus_table(corpus)}

## Metric 1 — R1 claim-overlap (Jaccard)

Lower = more diverse. Pairwise Jaccard averaged per debate, then
averaged per cell.

{_twoxtwo_jaccard(summaries)}

## Metric 2 — Synthesis-vs-best-R1 preference (90% CI)

Fraction of debates where the judge preferred the final synthesis over
the strongest R1 answer. Ties = 0.5.

{_twoxtwo_preference(summaries)}

## Interpretation

{verdict_md}

## Caveats

- Thresholds above are hypotheses, not tuned. Calibrate at n ≥ 30.
- Single judge (default gemini-2.5-flash). Replicate with
  `scripts/judge_replication.py` using GPT-5 and Claude Sonnet as
  judges to rule out judge-family bias.
- Persona text is provisional (skeptic / implementer / strategist);
  rerun with alternative persona sets before drawing conclusions.
- Slot-to-persona mapping is fixed; persona-model interaction effects
  may be present and would need a separate crossed design to isolate.

## Appendix — per-debate details

{appendix}

## Run metadata

Run id: `{run_id}` · Report generated: {date_str}
"""

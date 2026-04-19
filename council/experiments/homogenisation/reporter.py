"""Phase 3 of the homogenisation probe: render the markdown report
from scored data.

Pure data transform. The heavy lifting is the interpretation table —
it converts per-roster summaries into a plain-English verdict using
the thresholds documented in the spec. Everything else is formatting.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

from council.experiments.homogenisation.corpus import CorpusPrompt
from council.experiments.homogenisation.rosters import RosterSpec

_QUESTION_VERBATIM = (
    "All three current elders (Claude Opus, Gemini Pro, GPT-5) are trained "
    "on heavily overlapping web data and RLHF'd toward similar behaviours. "
    "Does the tool's value come from model diversity, from the debate "
    "protocol, from both, or from neither?"
)


def _interpret(summaries: list[dict[str, Any]]) -> list[str]:
    """Turn per-roster summaries into verdict bullets."""
    by_name = {s["roster"]: s for s in summaries}
    bullets: list[str] = []
    hom = by_name.get("homogeneous")
    mix = by_name.get("mixed_baseline")
    sub = by_name.get("substituted")

    if hom and mix:
        gap = hom["mean_r1_jaccard"] - mix["mean_r1_jaccard"]
        if gap < 0.05:
            bullets.append(
                f"Model diversity produces negligible R1 variance on this corpus "
                f"(homogeneous−mixed Jaccard gap = {gap:+.3f}; threshold 0.05)."
            )
        else:
            bullets.append(
                f"Mixed roster has measurably lower R1 claim-overlap than the "
                f"homogeneous control (gap = {gap:+.3f}) — model diversity matters."
            )
    if mix and sub:
        gap = mix["mean_r1_jaccard"] - sub["mean_r1_jaccard"]
        if gap > 0.10:
            bullets.append(
                f"Open-weights substitution adds meaningful diversity beyond the "
                f"same-lineage trio (mixed−substituted gap = {gap:+.3f})."
            )
        else:
            bullets.append(
                f"Open-weights substitution does not measurably widen diversity "
                f"(mixed−substituted gap = {gap:+.3f}; threshold 0.10)."
            )
    if hom and mix:
        pref_gap = mix["preference_rate"] - hom["preference_rate"]
        if pref_gap > 0.10:
            bullets.append(
                f"Tool's value appears to depend on both mechanisms — mixed "
                f"synthesis-preference exceeds homogeneous by {pref_gap:+.3f}."
            )
        elif abs(pref_gap) <= 0.10:
            bullets.append(
                f"Debate protocol alone does most of the work — homogeneous "
                f"and mixed preference rates are within ±0.10 ({pref_gap:+.3f})."
            )
        else:
            # pref_gap < -0.10: unexpected direction (mixed < homogeneous).
            bullets.append(
                f"Unexpected result: homogeneous roster's synthesis-preference "
                f"exceeds mixed baseline by {-pref_gap:+.3f} — inspect judge "
                f"behaviour or corpus shape before interpreting."
            )
    return bullets


def _rosters_table(rosters: tuple[RosterSpec, ...]) -> str:
    rows = ["| Roster | claude slot | gemini slot | chatgpt slot |", "|---|---|---|---|"]
    for r in rosters:
        rows.append(
            f"| `{r.name}` | `{r.models['claude']}` | "
            f"`{r.models['gemini']}` | `{r.models['chatgpt']}` |"
        )
    return "\n".join(rows)


def _corpus_table(corpus: list[CorpusPrompt]) -> str:
    rows = ["| id | shape | prompt |", "|---|---|---|"]
    for p in corpus:
        rows.append(f"| `{p.id}` | {p.shape} | {p.prompt} |")
    return "\n".join(rows)


def _jaccard_table(summaries: list[dict[str, Any]]) -> str:
    rows = ["| Roster | n | mean R1 Jaccard | median |", "|---|---|---|---|"]
    for s in summaries:
        rows.append(
            f"| `{s['roster']}` | {s['n_debates']} | "
            f"{s['mean_r1_jaccard']:.3f} | {s['median_r1_jaccard']:.3f} |"
        )
    return "\n".join(rows)


def _preference_table(summaries: list[dict[str, Any]]) -> str:
    rows = ["| Roster | n | pref rate | 90% CI |", "|---|---|---|---|"]
    for s in summaries:
        rows.append(
            f"| `{s['roster']}` | {s['n_debates']} | {s['preference_rate']:.3f} | "
            f"[{s['preference_ci_lo']:.3f}, {s['preference_ci_hi']:.3f}] |"
        )
    return "\n".join(rows)


def _appendix(rows: list[dict[str, Any]]) -> str:
    lines = ["| debate | roster | prompt | R1 Jaccard | winner |",
             "|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| `{r['debate_id'][:8]}` | {r['roster']} | {r['prompt_id']} | "
            f"{r['r1_jaccard']:.3f} | {r['preference_winner']} |"
        )
    return "\n".join(lines)


def render_report(
    *,
    scores_path: Path,
    corpus: list[CorpusPrompt],
    rosters: tuple[RosterSpec, ...],
    run_id: str,
) -> str:
    data = json.loads(scores_path.read_text())
    rows: list[dict[str, Any]] = data["rows"]
    summaries: list[dict[str, Any]] = data["summaries"]
    date_str = _dt.date.today().isoformat()
    verdict_bullets = _interpret(summaries)
    verdict_md = "\n".join(f"- {b}" for b in verdict_bullets) or "- (no data)"

    return f"""# Model homogenisation probe — {date_str}

Run id: `{run_id}`

## Question

{_QUESTION_VERBATIM}

## Rosters tested

{_rosters_table(rosters)}

## Corpus

{_corpus_table(corpus)}

## Results

### Metric 1 — R1 claim-overlap (Jaccard)

Lower = more diverse. Pairwise Jaccard averaged per debate, then averaged across corpus per roster.

{_jaccard_table(summaries)}

### Metric 2 — Synthesis-vs-best-R1 preference

Fraction of debates where the judge preferred the final synthesis over the strongest R1 answer. Ties counted as 0.5. 90% binomial (Wilson) CI.

{_preference_table(summaries)}

## Interpretation

{verdict_md}

## Caveats

- Small n (8 prompts); results directional, not significance-tested.
- Single judge model (gemini-2.5-flash). Internally consistent; absolute numbers not portable to other judges.
- One open-weights substitute (Llama-3.1-70B), one homogeneous model (gpt-5-mini). Other choices could give different numbers.
- gemini slot substituted; other slots not swept.
- Round cap 6 may truncate debates; reported, not mitigated.
- Judge family proximity — gemini-flash may bias toward gemini-slot content in mixed/substituted rosters.
- Persona priming: homogeneous elders still see peers labelled as "Claude"/"Gemini"/"ChatGPT" via the existing prompt pack, so this is not a clean model-equivalence test — it is the operational behaviour a user configuring 3× same-model would see.

## Appendix A — per-debate details

{_appendix(rows)}

## Appendix B — run metadata

Run id: `{run_id}` · Report generated: {date_str}
"""

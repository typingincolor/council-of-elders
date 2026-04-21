#!/usr/bin/env python3
"""CLI entrypoint for the format ablation.

Tests two independent format interventions against the r1_only baseline
established by the 2026-04-20-226f debate-depth ablation:

- ``alt_synth``     — R1 only + free-form synthesis prompt (drops the
                      ANSWER/WHY/DISAGREEMENTS structure).
- ``silent_revise`` — R1 + silent-revise R2 (elders privately re-write
                      their own R1 after reading peers, no convergence/
                      questions), current synthesis prompt.

Usage::

    python scripts/format_ablation.py run [--run-id ...]
    python scripts/format_ablation.py score --run-id ...
    python scripts/format_ablation.py report --run-id ...

Requires OPENROUTER_API_KEY (env or ``~/.council/config.toml``).
Reuses the diversity_split multi-judge scorer for scoring.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from council.adapters.elders.openrouter import OpenRouterAdapter  # noqa: E402
from council.app.config import load_config  # noqa: E402
from council.domain.models import ElderId  # noqa: E402
from council.domain.roster import RosterSpec  # noqa: E402
from council.experiments.diversity_split.scorer import score_probe_multi  # noqa: E402
from council.experiments.format_ablation.runner import VARIANTS, run_format_ablation  # noqa: E402
from council.experiments.homogenisation.corpus import load_corpus  # noqa: E402

DEFAULT_SINGLE_JUDGE = "google/gemini-2.5-flash"
DEFAULT_PREFERENCE_JUDGES = "google/gemini-2.5-flash,anthropic/claude-haiku-4.5"
DEFAULT_RUNS_ROOT = Path("runs")
DEFAULT_CORPUS = Path("scripts/homogenisation_corpus.json")
DEFAULT_REPORTS_ROOT = Path("docs/experiments")

# Same diff_model roster as the depth ablation so the baseline_r1_only
# cell is directly comparable to the 2026-04-20-226f r1_only result
# (0.375 preference rate after the synthesis-parsing fix).
FORMAT_ABLATION_ROSTER = RosterSpec(
    name="diff_model",
    models={
        "ada": "anthropic/claude-sonnet-4.5",
        "kai": "meta-llama/llama-3.1-70b-instruct",
        "mei": "openai/gpt-5",
    },
)


def _new_run_id() -> str:
    return f"{date.today().isoformat()}-{secrets.token_hex(2)}"


def _require_key() -> str:
    config = load_config()
    if not config.openrouter_api_key:
        raise SystemExit(
            "OPENROUTER_API_KEY not resolvable; set the env var or put it "
            "in ~/.council/config.toml before running the ablation."
        )
    return config.openrouter_api_key


def _build_elders(api_key: str) -> dict[ElderId, OpenRouterAdapter]:
    return {
        slot: OpenRouterAdapter(elder_id=slot, model=model, api_key=api_key)
        for slot, model in FORMAT_ABLATION_ROSTER.models.items()
    }


async def _cmd_run(args: argparse.Namespace) -> None:
    api_key = _require_key()
    prompts = load_corpus(Path(args.corpus))

    def factory():
        return _build_elders(api_key)

    manifest_path = await run_format_ablation(
        variants=VARIANTS,
        roster=FORMAT_ABLATION_ROSTER,
        prompts=prompts,
        run_id=args.run_id,
        runs_root=Path(args.runs_root),
        debate_store_root=Path.home() / ".council" / "debates",
        elder_factory=factory,  # type: ignore[arg-type]
    )
    print(f"Run complete. Manifest: {manifest_path}")


async def _cmd_score(args: argparse.Namespace) -> None:
    api_key = _require_key()
    single_judge = OpenRouterAdapter(
        elder_id="ada",
        model=args.judge_model,
        api_key=api_key,
    )
    preference_judge_models = [m.strip() for m in args.preference_judges.split(",") if m.strip()]
    preference_judges = [
        (m, OpenRouterAdapter(elder_id="ada", model=m, api_key=api_key))
        for m in preference_judge_models
    ]
    print(f"Single judge (jaccard/best-R1): {args.judge_model}")
    print(f"Preference judges ({len(preference_judges)}): {preference_judge_models}")
    path = await score_probe_multi(
        run_id=args.run_id,
        runs_root=Path(args.runs_root),
        debate_store_root=Path.home() / ".council" / "debates",
        single_judge=single_judge,
        preference_judges=preference_judges,
        seed=args.seed,
    )
    print(f"Scoring complete. Scores: {path}")


def _render_report(scores_path: Path, run_id: str) -> str:
    """Minimal markdown report. Each variant compared to baseline r1_only."""
    data = json.loads(scores_path.read_text())
    rows = data.get("rows", [])
    summaries = data.get("summaries", [])
    order = {"baseline_r1_only": 0, "alt_synth": 1, "silent_revise": 2}
    summaries = sorted(summaries, key=lambda s: order.get(s["roster"], 99))

    lines = [
        f"# Format ablation — {date.today().isoformat()}",
        "",
        f"Run id: `{run_id}`",
        "",
        "## Question",
        "",
        "The 2026-04-20-226f depth ablation showed R1-only-then-synthesise "
        "beating full debate for the diff_model roster. This experiment "
        "tests whether two independent format interventions move the "
        "needle further: a free-form synthesis prompt, and a silent-revise "
        "R2 where each elder privately re-writes their own answer after "
        "reading peers' R1s.",
        "",
        "## Roster (fixed)",
        "",
        "| slot | model |",
        "|---|---|",
        f"| ada | `{FORMAT_ABLATION_ROSTER.models['ada']}` |",
        f"| kai | `{FORMAT_ABLATION_ROSTER.models['kai']}` |",
        f"| mei | `{FORMAT_ABLATION_ROSTER.models['mei']}` |",
        "",
        "## Variants",
        "",
        "- `baseline_r1_only` — R1 only, current synthesis prompt "
        "(ANSWER/WHY/DISAGREEMENTS). Re-run here for apples-to-apples scoring.",
        "- `alt_synth` — R1 only, free-form synthesis prompt.",
        "- `silent_revise` — R1 + silent-revise R2 + current synthesis prompt.",
        "",
        "## Results",
        "",
        "| Variant | n | mean R1 Jaccard | pref rate | 90% CI |",
        "|---|---:|---:|---:|---|",
    ]
    by_variant = {s["roster"]: s for s in summaries}
    for v in ("baseline_r1_only", "alt_synth", "silent_revise"):
        s = by_variant.get(v)
        if s is None:
            lines.append(f"| `{v}` | — | — | — | — |")
            continue
        lines.append(
            f"| `{v}` | {s['n_debates']} | "
            f"{s['mean_r1_jaccard']:.3f} | {s['preference_rate']:.3f} | "
            f"[{s['preference_ci_lo']:.3f}, {s['preference_ci_hi']:.3f}] |"
        )
    lines.append("")

    # Verdict — each variant vs baseline.
    lines.append("## Verdict")
    lines.append("")
    base = by_variant.get("baseline_r1_only", {}).get("preference_rate")
    alt = by_variant.get("alt_synth", {}).get("preference_rate")
    sr = by_variant.get("silent_revise", {}).get("preference_rate")

    def _verdict(name: str, rate: float | None) -> str:
        if rate is None or base is None:
            return f"- `{name}` — incomplete; no verdict."
        gap = rate - base
        if gap > 0.10:
            return f"- **`{name}` moves the needle** (Δ vs baseline = {gap:+.3f})."
        if gap < -0.10:
            return f"- **`{name}` hurts** (Δ vs baseline = {gap:+.3f})."
        return f"- `{name}` is a wash vs baseline (Δ = {gap:+.3f}, within ±0.10)."

    lines.append(_verdict("alt_synth", alt))
    lines.append(_verdict("silent_revise", sr))
    lines.append("")

    lines.append("## Per-debate details")
    lines.append("")
    lines.append("| debate | variant | prompt | R1 Jaccard | winner | unanimous |")
    lines.append("|---|---|---|---:|---|---|")
    for r in rows:
        lines.append(
            f"| `{r['debate_id'][:8]}` | {r['roster']} | {r['prompt_id']} | "
            f"{r['r1_jaccard']:.3f} | {r['preference_winner']} | "
            f"{'yes' if r.get('preference_unanimous') else 'split'} |"
        )
    return "\n".join(lines)


def _cmd_report(args: argparse.Namespace) -> None:
    scores_path = Path(args.runs_root) / args.run_id / "scores.json"
    md = _render_report(scores_path, args.run_id)
    out = Path(args.reports_root) / f"{args.run_id}-format-ablation.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    print(f"Report written: {out}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="format_ablation")
    parser.add_argument(
        "--runs-root",
        default=str(DEFAULT_RUNS_ROOT),
        help=f"Where manifest/scores live (default: {DEFAULT_RUNS_ROOT})",
    )
    parser.add_argument(
        "--corpus",
        default=str(DEFAULT_CORPUS),
        help=f"Corpus JSON (default: {DEFAULT_CORPUS})",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run debates across the format variants")
    run_p.add_argument("--run-id", default=None)

    score_p = sub.add_parser("score", help="Score an existing run")
    score_p.add_argument("--run-id", required=True)
    score_p.add_argument(
        "--judge-model",
        default=DEFAULT_SINGLE_JUDGE,
        help=f"Single judge for claim-overlap and best-R1. Default: {DEFAULT_SINGLE_JUDGE}.",
    )
    score_p.add_argument(
        "--preference-judges",
        default=DEFAULT_PREFERENCE_JUDGES,
        help=f"Comma-separated preference judges. Default: {DEFAULT_PREFERENCE_JUDGES}.",
    )
    score_p.add_argument("--seed", type=int, default=0)

    rep_p = sub.add_parser("report", help="Render markdown report")
    rep_p.add_argument("--run-id", required=True)
    rep_p.add_argument("--reports-root", default=str(DEFAULT_REPORTS_ROOT))

    args = parser.parse_args()
    if args.cmd == "run":
        if args.run_id is None:
            args.run_id = _new_run_id()
            print(f"New run id: {args.run_id}")
        asyncio.run(_cmd_run(args))
    elif args.cmd == "score":
        asyncio.run(_cmd_score(args))
    elif args.cmd == "report":
        _cmd_report(args)


if __name__ == "__main__":
    main()

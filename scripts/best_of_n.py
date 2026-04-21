#!/usr/bin/env python3
"""Best-of-N vs synthesis comparison.

Reuses an existing run's stored debates (no new elder calls): for each
debate, has multi-judge pick the strongest R1 answer, then compares
that pick head-to-head against the synthesis output via the same
preference-judge pipeline the main scorer uses.

Answers: "if we productionised 'fan out to 3 LLMs, multi-judge picks
best' instead of synthesis, would users prefer the output?"

Usage::

    python scripts/best_of_n.py run --source-run-id 2026-04-21-f13d

Output: ``runs/<source-run-id>/best_of_n.json`` + a markdown report at
``docs/experiments/<source-run-id>-best-of-n.md``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from council.adapters.elders.openrouter import OpenRouterAdapter  # noqa: E402
from council.adapters.storage.json_file import JsonFileStore  # noqa: E402
from council.app.config import load_config  # noqa: E402
from council.domain.models import ElderId  # noqa: E402
from council.domain.preference import judge_preference_multi  # noqa: E402
from council.domain.synthesis_output import parse_synthesis  # noqa: E402
from council.experiments.homogenisation.judges import judge_best_r1  # noqa: E402
from council.experiments.homogenisation.scorer import _binomial_ci_90  # noqa: E402

DEFAULT_PREFERENCE_JUDGES = "google/gemini-2.5-flash,anthropic/claude-haiku-4.5"
DEFAULT_RUNS_ROOT = Path("runs")
DEFAULT_REPORTS_ROOT = Path("docs/experiments")

_ELDER_ORDER: tuple[ElderId, ElderId, ElderId] = ("ada", "kai", "mei")


@dataclass(frozen=True)
class BestOfNRow:
    debate_id: str
    roster: str  # reused as the variant/grouping key from the source manifest
    prompt_id: str
    # Per-judge best-R1 pick (1, 2, or 3 — the elder index in _ELDER_ORDER).
    judge_picks: list[dict[str, int | str]]
    # Final multi-judge pick after majority/tie-break.
    multi_pick_index: int
    multi_pick_elder: str
    multi_pick_unanimous: bool
    # Head-to-head vs synthesis (best_of_n_pick as "best_r1" side of the rubric).
    preference_winner: str  # "synthesis" | "best_r1" | "tie"
    preference_unanimous: bool


@dataclass(frozen=True)
class GroupSummary:
    roster: str
    n: int
    # Best-of-N preference = 1.0 - synthesis_preference. Reported directly
    # so the table reads from the best-of-N perspective.
    best_of_n_preference_rate: float
    best_of_n_ci_lo: float
    best_of_n_ci_hi: float
    synthesis_wins: int
    best_of_n_wins: int
    ties: int


def _require_key() -> str:
    config = load_config()
    if not config.openrouter_api_key:
        raise SystemExit(
            "OPENROUTER_API_KEY not resolvable; set the env var or put it in "
            "~/.council/config.toml before running best-of-N."
        )
    return config.openrouter_api_key


async def _multi_judge_best_r1(
    *,
    question: str,
    answers: tuple[str, str, str],
    judges: list[tuple[str, object]],
) -> tuple[int, bool, list[dict[str, int | str]]]:
    """Run judge_best_r1 with each judge. Majority vote on the pick;
    deterministic tie-break using the first judge's pick.
    Returns (picked_index, unanimous, per-judge records).
    """
    picks: list[int] = []
    records: list[dict[str, int | str]] = []
    for model_id, port in judges:
        obs = await judge_best_r1(question=question, answers=answers, judge_port=port)
        picks.append(obs.best_index)
        records.append({"judge_model": model_id, "best_index": obs.best_index})
    counts = Counter(picks)
    (top_idx, top_count), *rest = counts.most_common()
    if rest and rest[0][1] == top_count:
        # Tie between judges — fall back to first judge's pick.
        return picks[0], False, records
    return top_idx, (top_count == len(picks)), records


async def _run(args: argparse.Namespace) -> Path:
    api_key = _require_key()
    source_run_id = args.source_run_id
    manifest_path = Path(args.runs_root) / source_run_id / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"No manifest at {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    entries = manifest["entries"]
    if args.variant:
        entries = [e for e in entries if e["roster"] == args.variant]
        if not entries:
            raise SystemExit(f"No entries with roster={args.variant} in {manifest_path}")

    judge_models = [m.strip() for m in args.preference_judges.split(",") if m.strip()]
    judges = [
        (m, OpenRouterAdapter(elder_id="ada", model=m, api_key=api_key)) for m in judge_models
    ]
    print(f"Source run: {source_run_id} ({len(entries)} entries)")
    print(f"Judges ({len(judges)}): {judge_models}")

    store = JsonFileStore(root=Path.home() / ".council" / "debates")
    rng = random.Random(args.seed)

    out_path = Path(args.runs_root) / source_run_id / "best_of_n.json"
    # Idempotent: preserve existing rows for already-processed debates.
    existing: dict[str, dict] = {}
    if out_path.exists() and not args.force:
        existing = {r["debate_id"]: r for r in json.loads(out_path.read_text()).get("rows", [])}

    rows: list[dict] = []
    for entry in entries:
        debate_id = entry["debate_id"]
        if debate_id in existing:
            rows.append(existing[debate_id])
            _write(out_path, rows)
            continue
        debate = store.load(debate_id)
        if not debate.rounds:
            print(f"  skip {debate_id}: no R1")
            continue
        r1 = {t.elder: (t.answer.text or "") for t in debate.rounds[0].turns}
        answers = tuple(r1[e] for e in _ELDER_ORDER)

        pick_idx, pick_unanimous, pick_records = await _multi_judge_best_r1(
            question=debate.prompt,
            answers=answers,
            judges=judges,
        )
        pick_text = answers[pick_idx - 1]
        pick_elder = _ELDER_ORDER[pick_idx - 1]

        raw_synth = debate.synthesis.text if debate.synthesis else ""
        synth_text = parse_synthesis(raw_synth).answer if raw_synth else ""

        pref = await judge_preference_multi(
            question=debate.prompt,
            synthesis=synth_text,
            best_r1=pick_text,
            judges=judges,
            rng=rng,
        )
        row = BestOfNRow(
            debate_id=debate_id,
            roster=entry["roster"],
            prompt_id=entry["prompt_id"],
            judge_picks=pick_records,
            multi_pick_index=pick_idx,
            multi_pick_elder=pick_elder,
            multi_pick_unanimous=pick_unanimous,
            preference_winner=pref.aggregate,
            preference_unanimous=pref.unanimous,
        )
        rows.append(asdict(row))
        _write(out_path, rows)
        print(
            f"  {debate_id[:8]} {entry['roster']}/{entry['prompt_id']}: "
            f"pick={pick_elder}(#{pick_idx}) "
            f"{'u' if pick_unanimous else 'split'} → "
            f"{pref.aggregate}"
        )
    _write(out_path, rows)
    print(f"Wrote {out_path}")
    return out_path


def _write(path: Path, rows: list[dict]) -> None:
    summaries = [asdict(s) for s in _summarise(rows)]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps({"rows": rows, "summaries": summaries}, indent=2))
    tmp.replace(path)


def _summarise(rows: list[dict]) -> list[GroupSummary]:
    by_roster: dict[str, list[dict]] = {}
    for r in rows:
        by_roster.setdefault(r["roster"], []).append(r)
    out: list[GroupSummary] = []
    for name, group in sorted(by_roster.items()):
        n = len(group)
        synth = sum(1 for g in group if g["preference_winner"] == "synthesis")
        bon = sum(1 for g in group if g["preference_winner"] == "best_r1")
        ties = n - synth - bon
        # Best-of-N preference: wins count 1.0, ties 0.5.
        score = bon + 0.5 * ties
        rate = score / n if n else 0.0
        lo, hi = _binomial_ci_90(successes=round(score), n=n)
        out.append(
            GroupSummary(
                roster=name,
                n=n,
                best_of_n_preference_rate=rate,
                best_of_n_ci_lo=lo,
                best_of_n_ci_hi=hi,
                synthesis_wins=synth,
                best_of_n_wins=bon,
                ties=ties,
            )
        )
    return out


def _render_report(out_path: Path, source_run_id: str) -> str:
    data = json.loads(out_path.read_text())
    rows = data["rows"]
    summaries = data["summaries"]
    # Agreement rate between judges on the best_r1 pick.
    unanimous_picks = sum(1 for r in rows if r["multi_pick_unanimous"])
    agreement = unanimous_picks / len(rows) if rows else 0.0

    lines = [
        f"# Best-of-N vs synthesis — {source_run_id}",
        "",
        f"Source run: `{source_run_id}` (reusing stored debates — no new elder calls).",
        "",
        "## Question",
        "",
        "If the tool switched from synthesis to 'fan out to 3 LLMs, "
        "multi-judge picks the strongest R1', would a separate "
        "preference judge prefer the output over the current synthesis?",
        "",
        "## Method",
        "",
        "For each debate in the source run:",
        "",
        "1. Load the stored R1 answers and the existing synthesis.",
        "2. Each preference judge (gemini-2.5-flash + claude-haiku-4.5) "
        "independently picks the strongest R1. Majority vote; on judge "
        "disagreement, fall back to the first judge's pick.",
        "3. Head-to-head: judge_preference_multi compares the picked R1 "
        "to the parsed synthesis ANSWER body. Same rubric and same two "
        "judges as the main scorer uses.",
        "",
        f"Inter-judge agreement on the best-R1 pick: **{agreement:.1%}** "
        f"({unanimous_picks}/{len(rows)} debates).",
        "",
        "## Results",
        "",
        "Preference rate is reported from the **best-of-N** perspective "
        "(wins count 1.0, ties 0.5). A rate above 0.5 means best-of-N is "
        "preferred over synthesis on average.",
        "",
        "| Variant | n | best-of-N pref | 90% CI | BoN wins | ties | synth wins |",
        "|---|---:|---:|---|---:|---:|---:|",
    ]
    for s in summaries:
        lines.append(
            f"| `{s['roster']}` | {s['n']} | "
            f"{s['best_of_n_preference_rate']:.3f} | "
            f"[{s['best_of_n_ci_lo']:.3f}, {s['best_of_n_ci_hi']:.3f}] | "
            f"{s['best_of_n_wins']} | {s['ties']} | {s['synthesis_wins']} |"
        )
    lines.append("")

    lines.append("## Verdict")
    lines.append("")
    for s in summaries:
        rate = s["best_of_n_preference_rate"]
        gap = rate - 0.5
        if gap > 0.10:
            lines.append(
                f"- **`{s['roster']}`: best-of-N is preferred over synthesis** "
                f"(rate {rate:.3f}, Δ vs break-even = {gap:+.3f})."
            )
        elif gap < -0.10:
            lines.append(
                f"- **`{s['roster']}`: synthesis is preferred over best-of-N** "
                f"(rate {rate:.3f}, Δ vs break-even = {gap:+.3f})."
            )
        else:
            lines.append(
                f"- `{s['roster']}`: best-of-N and synthesis are approximately "
                f"equivalent (rate {rate:.3f}, within ±0.10 of break-even)."
            )
    lines.append("")

    lines.append("## Per-debate details")
    lines.append("")
    lines.append("| debate | variant | prompt | pick | unanimous pick | winner |")
    lines.append("|---|---|---|---|---|---|")
    for r in rows:
        lines.append(
            f"| `{r['debate_id'][:8]}` | {r['roster']} | {r['prompt_id']} | "
            f"{r['multi_pick_elder']} | {'yes' if r['multi_pick_unanimous'] else 'split'} | "
            f"{r['preference_winner']} |"
        )
    return "\n".join(lines)


def _cmd_report(args: argparse.Namespace) -> None:
    out_path = Path(args.runs_root) / args.source_run_id / "best_of_n.json"
    md = _render_report(out_path, args.source_run_id)
    report_path = Path(args.reports_root) / f"{args.source_run_id}-best-of-n.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(md)
    print(f"Report written: {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="best_of_n")
    parser.add_argument("--runs-root", default=str(DEFAULT_RUNS_ROOT))
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Score an existing run with best-of-N")
    run_p.add_argument("--source-run-id", required=True)
    run_p.add_argument("--variant", default=None, help="Restrict to one roster/variant")
    run_p.add_argument(
        "--preference-judges",
        default=DEFAULT_PREFERENCE_JUDGES,
        help=f"Comma-separated preference judges. Default: {DEFAULT_PREFERENCE_JUDGES}.",
    )
    run_p.add_argument("--seed", type=int, default=0)
    run_p.add_argument("--force", action="store_true", help="Ignore existing rows")

    rep_p = sub.add_parser("report", help="Render markdown report")
    rep_p.add_argument("--source-run-id", required=True)
    rep_p.add_argument("--reports-root", default=str(DEFAULT_REPORTS_ROOT))

    args = parser.parse_args()
    if args.cmd == "run":
        asyncio.run(_run(args))
    elif args.cmd == "report":
        _cmd_report(args)


if __name__ == "__main__":
    main()

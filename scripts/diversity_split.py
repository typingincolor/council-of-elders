#!/usr/bin/env python3
"""CLI entrypoint for the diversity-split 2×2 experiment.

    python scripts/diversity_split.py run --run-id 2026-04-20-abcd
    python scripts/diversity_split.py score --run-id 2026-04-20-abcd
    python scripts/diversity_split.py report --run-id 2026-04-20-abcd

Requires OPENROUTER_API_KEY (env or ``~/.council/config.toml``).

Layered on the homogenisation probe's infrastructure — same corpus,
same scorer, same judge. The only difference is the condition matrix:
four (roster × pack) cells instead of three roster variants.
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from council.adapters.elders.openrouter import OpenRouterAdapter  # noqa: E402
from council.app.config import load_config  # noqa: E402
from council.domain.models import ElderId  # noqa: E402
from council.experiments.diversity_split.conditions import (  # noqa: E402
    CONDITIONS,
    Condition,
)
from council.experiments.diversity_split.reporter import render_report  # noqa: E402
from council.experiments.diversity_split.runner import run_experiment  # noqa: E402
from council.experiments.diversity_split.scorer import score_probe_multi  # noqa: E402
from council.experiments.homogenisation.corpus import load_corpus  # noqa: E402

DEFAULT_SINGLE_JUDGE = "google/gemini-2.5-flash"
DEFAULT_PREFERENCE_JUDGES = "google/gemini-2.5-flash,anthropic/claude-haiku-4.5"
DEFAULT_RUNS_ROOT = Path("runs")
DEFAULT_CORPUS = Path("scripts/homogenisation_corpus.json")
DEFAULT_REPORTS_ROOT = Path("docs/experiments")


def _new_run_id() -> str:
    return f"{date.today().isoformat()}-{secrets.token_hex(2)}"


def _require_key() -> str:
    config = load_config()
    if not config.openrouter_api_key:
        raise SystemExit(
            "OPENROUTER_API_KEY not resolvable; set the env var or put it "
            "in ~/.council/config.toml before running the experiment."
        )
    return config.openrouter_api_key


def _build_elders(condition: Condition, *, api_key: str):
    return {
        slot: OpenRouterAdapter(elder_id=slot, model=model, api_key=api_key)
        for slot, model in condition.roster.models.items()
    }


async def _cmd_run(args: argparse.Namespace) -> None:
    api_key = _require_key()
    prompts = load_corpus(Path(args.corpus))

    def factory(condition: Condition) -> dict[ElderId, object]:
        return _build_elders(condition, api_key=api_key)

    manifest_path = await run_experiment(
        conditions=CONDITIONS,
        prompts=prompts,
        run_id=args.run_id,
        runs_root=Path(args.runs_root),
        debate_store_root=Path.home() / ".council" / "debates",
        elder_factory=factory,  # type: ignore[arg-type]
        max_rounds=args.max_rounds,
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
        (
            m,
            OpenRouterAdapter(elder_id="ada", model=m, api_key=api_key),
        )
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


def _cmd_report(args: argparse.Namespace) -> None:
    prompts = load_corpus(Path(args.corpus))
    scores_path = Path(args.runs_root) / args.run_id / "scores.json"
    md = render_report(
        scores_path=scores_path,
        corpus=prompts,
        conditions=CONDITIONS,
        run_id=args.run_id,
    )
    out = Path(args.reports_root) / f"{args.run_id}-diversity-split.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    print(f"Report written: {out}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="diversity_split")
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

    run_p = sub.add_parser("run", help="Run debates across the 2×2 conditions")
    run_p.add_argument("--run-id", default=None)
    run_p.add_argument("--max-rounds", type=int, default=6)

    score_p = sub.add_parser("score", help="Score an existing run")
    score_p.add_argument("--run-id", required=True)
    score_p.add_argument(
        "--judge-model",
        default=DEFAULT_SINGLE_JUDGE,
        help=(
            f"Single judge for claim-overlap and best-R1 rubrics. Default: {DEFAULT_SINGLE_JUDGE}."
        ),
    )
    score_p.add_argument(
        "--preference-judges",
        default=DEFAULT_PREFERENCE_JUDGES,
        help=(
            "Comma-separated OpenRouter model ids for preference scoring. "
            f"Default: {DEFAULT_PREFERENCE_JUDGES}. Multi-judge by default "
            "to avoid judge-family bias."
        ),
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

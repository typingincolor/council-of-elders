#!/usr/bin/env python3
"""CLI entrypoint for the homogenisation probe.

    python scripts/homogenisation_probe.py run --run-id 2026-04-19-abcd
    python scripts/homogenisation_probe.py score --run-id 2026-04-19-abcd
    python scripts/homogenisation_probe.py report --run-id 2026-04-19-abcd

Requires OPENROUTER_API_KEY (env or ~/.council/config.toml).
See docs/superpowers/specs/2026-04-19-issue-11-homogenisation-test-design.md.
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys
from datetime import date
from pathlib import Path

# Make the `council` package importable when running as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from council.adapters.elders.openrouter import OpenRouterAdapter  # noqa: E402
from council.app.config import load_config  # noqa: E402
from council.experiments.homogenisation.corpus import load_corpus  # noqa: E402
from council.experiments.homogenisation.reporter import render_report  # noqa: E402
from council.experiments.homogenisation.rosters import (  # noqa: E402
    ROSTERS,
    build_roster_elders,
)
from council.experiments.homogenisation.runner import run_probe  # noqa: E402
from council.experiments.homogenisation.scorer import score_probe  # noqa: E402

DEFAULT_JUDGE_MODEL = "google/gemini-2.5-flash"
DEFAULT_RUNS_ROOT = Path("runs")
DEFAULT_CORPUS = Path("scripts/homogenisation_corpus.json")
DEFAULT_REPORTS_ROOT = Path("docs/experiments")


def _new_run_id() -> str:
    return f"{date.today().isoformat()}-{secrets.token_hex(2)}"


def _require_key() -> str:
    config = load_config()
    if not config.openrouter_api_key:
        raise SystemExit(
            "OPENROUTER_API_KEY not resolvable; set the env var or put it in "
            "~/.council/config.toml before running the probe."
        )
    return config.openrouter_api_key


async def _cmd_run(args: argparse.Namespace) -> None:
    api_key = _require_key()
    prompts = load_corpus(Path(args.corpus))

    def factory(spec):  # noqa: ANN001 — RosterSpec
        return build_roster_elders(spec, api_key=api_key)

    manifest_path = await run_probe(
        rosters=ROSTERS,
        prompts=prompts,
        run_id=args.run_id,
        runs_root=Path(args.runs_root),
        debate_store_root=Path.home() / ".council" / "debates",
        elder_factory=factory,
        max_rounds=args.max_rounds,
    )
    print(f"Run complete. Manifest: {manifest_path}")


async def _cmd_score(args: argparse.Namespace) -> None:
    api_key = _require_key()
    judge = OpenRouterAdapter(
        elder_id="ada",
        model=args.judge_model,
        api_key=api_key,
    )
    path = await score_probe(
        run_id=args.run_id,
        runs_root=Path(args.runs_root),
        debate_store_root=Path.home() / ".council" / "debates",
        judge_port=judge,
        seed=args.seed,
    )
    print(f"Scoring complete. Scores: {path}")


def _cmd_report(args: argparse.Namespace) -> None:
    prompts = load_corpus(Path(args.corpus))
    scores_path = Path(args.runs_root) / args.run_id / "scores.json"
    md = render_report(
        scores_path=scores_path,
        corpus=prompts,
        rosters=ROSTERS,
        run_id=args.run_id,
    )
    out = Path(args.reports_root) / f"{args.run_id}-homogenisation.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    print(f"Report written: {out}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="homogenisation_probe")
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

    run_p = sub.add_parser("run", help="Phase 1 — run debates across rosters")
    run_p.add_argument("--run-id", default=None)
    run_p.add_argument("--max-rounds", type=int, default=6)

    score_p = sub.add_parser("score", help="Phase 2 — call judges, aggregate")
    score_p.add_argument("--run-id", required=True)
    score_p.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    score_p.add_argument("--seed", type=int, default=0)

    rep_p = sub.add_parser("report", help="Phase 3 — render markdown report")
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

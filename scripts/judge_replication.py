#!/usr/bin/env python3
"""Judge-swap replication for the homogenisation probe.

Re-scores an existing run with one or more alternative judges, writing
``scores-<judge-slug>.json`` alongside the original ``scores.json``.
This is the calibration path: if the probe's finding holds across GPT-5
and Claude-Sonnet judges as well as Gemini-Flash, the diversity-engine
architecture is defensible. If it doesn't, we have evidence of
judge-family bias and need to rethink.

Usage:

    python scripts/judge_replication.py --run-id 2026-04-19-9288 \\
        --judge-models openai/gpt-5,anthropic/claude-sonnet-4.5

Requires ``OPENROUTER_API_KEY`` (env or ``~/.council/config.toml``).
Reuses the existing ``council.experiments.homogenisation.scorer`` with
a per-judge side-output path so the primary ``scores.json`` is never
overwritten.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from council.adapters.elders.openrouter import OpenRouterAdapter  # noqa: E402
from council.app.config import load_config  # noqa: E402
from council.experiments.homogenisation.scorer import score_probe  # noqa: E402

DEFAULT_RUNS_ROOT = Path("runs")


def _slug(model_id: str) -> str:
    # "anthropic/claude-sonnet-4.5" → "anthropic-claude-sonnet-4-5"
    s = model_id.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _require_key() -> str:
    config = load_config()
    if not config.openrouter_api_key:
        raise SystemExit(
            "OPENROUTER_API_KEY not resolvable; set the env var or put it in "
            "~/.council/config.toml before running the judge-swap replication."
        )
    return config.openrouter_api_key


async def _run_for_judge(
    *, run_id: str, runs_root: Path, debate_store_root: Path, api_key: str, judge_model: str
) -> Path:
    judge = OpenRouterAdapter(elder_id="claude", model=judge_model, api_key=api_key)
    slug = _slug(judge_model)
    # Point the scorer at an alternate scores path so the original scores.json
    # for the gemini-flash judge stays intact.
    original_scores = runs_root / run_id / "scores.json"
    alt_scores = runs_root / run_id / f"scores-{slug}.json"

    # If a previous replication exists we pick it up as the starting point.
    # Swap files: rename scores.json aside, put alt_scores in its place,
    # call score_probe (which is idempotent), then restore.
    backup = None
    if original_scores.exists():
        backup = original_scores.read_bytes()
    if alt_scores.exists():
        original_scores.write_bytes(alt_scores.read_bytes())
    elif original_scores.exists():
        # Nothing to resume from — start from a clean slate for this judge.
        original_scores.unlink()

    try:
        await score_probe(
            run_id=run_id,
            runs_root=runs_root,
            debate_store_root=debate_store_root,
            judge_port=judge,
            seed=0,
        )
        # Move the just-written scores.json into the alt path.
        if original_scores.exists():
            alt_scores.write_bytes(original_scores.read_bytes())
    finally:
        # Restore the original gemini-flash scores.json.
        if backup is not None:
            original_scores.write_bytes(backup)
        elif original_scores.exists():
            original_scores.unlink()

    return alt_scores


async def _cmd_replicate(args: argparse.Namespace) -> None:
    api_key = _require_key()
    judge_models = [m.strip() for m in args.judge_models.split(",") if m.strip()]
    if not judge_models:
        raise SystemExit("Pass at least one --judge-models value.")
    runs_root = Path(args.runs_root)
    debate_store_root = Path.home() / ".council" / "debates"

    for jm in judge_models:
        print(f"Replicating with judge: {jm}")
        path = await _run_for_judge(
            run_id=args.run_id,
            runs_root=runs_root,
            debate_store_root=debate_store_root,
            api_key=api_key,
            judge_model=jm,
        )
        print(f"  → wrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="judge_replication")
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--runs-root", default=str(DEFAULT_RUNS_ROOT),
        help=f"Root directory for run manifests (default: {DEFAULT_RUNS_ROOT})",
    )
    parser.add_argument(
        "--judge-models", required=True,
        help=(
            "Comma-separated OpenRouter model ids to use as alternative "
            "judges. Example: "
            "openai/gpt-5,anthropic/claude-sonnet-4.5"
        ),
    )
    args = parser.parse_args()
    asyncio.run(_cmd_replicate(args))


if __name__ == "__main__":
    main()

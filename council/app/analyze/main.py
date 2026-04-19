"""`council-analyze` — run structural scorers on saved debate transcripts.

No LLM calls. Consumes saved JSON transcripts from ~/.council/debates/ and
emits a concise report of the failure-mode metrics the design-level
meta-debate flagged as priorities to measure before any architectural
redesign.

Usage:
    council-analyze <debate-id>
    council-analyze <debate-id-prefix>
    council-analyze all
"""

from __future__ import annotations

import argparse
import asyncio
import glob
from pathlib import Path

from council.adapters.storage.json_file import JsonFileStore
from council.app.config import load_config
from council.domain.debate_analytics import (
    DriftObservation,
    LatchingReport,
    LowDeltaReport,
    analyse_drift,
    analyse_latching,
    analyse_low_delta_rounds,
)
from council.domain.models import Debate

# Default judge model for the drift rubric. `:free` OpenRouter endpoints
# exist (e.g. meta-llama/llama-3.3-70b-instruct:free,
# google/gemma-2-9b-it:free) but availability is patchy — upstream
# providers rotate, rate limits hit fast, and some appear as 404 for
# certain accounts. gemini-2.5-flash is cheap enough (~$0.001 per debate)
# that "free" isn't a meaningful saving for corpus-scale analysis,
# and it's reliably available. Users who want a free tier can pass
# --judge-model anthropic/... or meta-llama/...:free and the code will
# handle it identically.
_DEFAULT_JUDGE_MODEL = "google/gemini-2.5-flash"


def _load_debates(store_root: Path, debate_id_or_prefix: str) -> list[Debate]:
    store = JsonFileStore(root=store_root)
    if debate_id_or_prefix == "all":
        paths = sorted(store_root.glob("*.json"))
        return [store.load(p.stem) for p in paths]
    # Try exact id first.
    exact = store_root / f"{debate_id_or_prefix}.json"
    if exact.exists():
        return [store.load(debate_id_or_prefix)]
    # Fall back to prefix match.
    matches = sorted(glob.glob(str(store_root / f"{debate_id_or_prefix}*.json")))
    if not matches:
        raise SystemExit(f"No debate matching {debate_id_or_prefix!r} under {store_root}")
    return [store.load(Path(p).stem) for p in matches]


def _print_debate_report(debate: Debate, drift: DriftObservation | None = None) -> None:
    latching: LatchingReport = analyse_latching(debate)
    low_delta: LowDeltaReport = analyse_low_delta_rounds(debate)

    short_prompt = debate.prompt.strip().split("\n", 1)[0]
    if len(short_prompt) > 80:
        short_prompt = short_prompt[:77] + "..."

    print(f"=== {debate.id[:8]} · {len(debate.rounds)} rounds · {short_prompt!r}")

    if latching.n == 0:
        print("  Latching: no CONVERGED:yes → peer-question → response triples found")
    else:
        print(
            f"  Latching: {latching.n} observation(s) · "
            f"substantive={latching.substantive_rate:.0%} · "
            f"disengaged={latching.disengaged_rate:.0%} · "
            f"flipped={latching.flip_rate:.0%}"
        )
        for obs in latching.observations:
            print(
                f"    · {obs.elder} converged R{obs.converged_round}, "
                f"probed by {obs.peer_asker} → R{obs.followup_round} "
                f"{obs.classification} ({obs.followup_body_chars} chars)"
            )

    if low_delta.n == 0:
        print("  Low-delta: no round-over-round comparisons (only R1 present)")
    else:
        print(
            f"  Low-delta rounds: {low_delta.low_delta_rate:.0%} of "
            f"{low_delta.n} elder-round comparisons"
        )
        for d in low_delta.deltas:
            if d.is_low_delta:
                print(f"    · {d.elder} R{d.round_number} sim={d.similarity:.2f} (near-paraphrase)")

    if drift is not None:
        drift_label = "DRIFTED" if drift.drift_flag else "on-topic"
        print(
            f"  Drift (LLM judge): {drift_label} · "
            f"shape_fit={drift.shape_fit}/3 · content_fit={drift.content_fit}/3"
        )
        print(f"    · {drift.reason}")

    print()


async def _judge_debates(
    debates: list[Debate], judge_model: str
) -> dict[str, DriftObservation | None]:
    """Run the drift rubric judge across a list of debates, returning a
    mapping from debate-id to observation (or None for skipped debates).
    """
    from council.adapters.elders.openrouter import OpenRouterAdapter

    config = load_config()
    if not config.openrouter_api_key:
        raise SystemExit(
            "OPENROUTER_API_KEY not resolvable; --judge requires a key in the "
            "TOML config or OPENROUTER_API_KEY env var."
        )

    judge = OpenRouterAdapter(
        elder_id="claude",  # elder_id is arbitrary; the judge is a standalone adapter
        model=judge_model,
        api_key=config.openrouter_api_key,
    )

    results: dict[str, DriftObservation | None] = {}
    for d in debates:
        try:
            obs = await analyse_drift(d, judge)
            results[d.id] = obs
        except Exception as ex:  # pragma: no cover — network/rate-limit path
            print(f"[warning] drift judge failed for {d.id[:8]}: {ex}")
            results[d.id] = None
    return results


def main() -> None:
    parser = argparse.ArgumentParser(prog="council-analyze")
    parser.add_argument(
        "target",
        help="Debate id, id prefix, or 'all' to analyse every saved debate.",
    )
    parser.add_argument(
        "--store-root",
        default=str(Path.home() / ".council" / "debates"),
    )
    parser.add_argument(
        "--judge",
        action="store_true",
        help="Run an LLM rubric judge to score each debate for task drift. "
        "Requires OPENROUTER_API_KEY. Off by default (adds one API call "
        "per debate).",
    )
    parser.add_argument(
        "--judge-model",
        default=_DEFAULT_JUDGE_MODEL,
        help=f"OpenRouter model ID for the drift judge. Default: {_DEFAULT_JUDGE_MODEL}. "
        "Try `:free` variants like `meta-llama/llama-3.3-70b-instruct:free` for "
        "zero-cost runs when available, but free endpoints are subject to "
        "rate limits and upstream rotation.",
    )
    args = parser.parse_args()

    debates = _load_debates(Path(args.store_root), args.target)
    if not debates:
        print("No debates found.")
        return

    drift_results: dict[str, DriftObservation | None] = {}
    if args.judge:
        print(f"Running drift judge ({args.judge_model}) across {len(debates)} debates...\n")
        drift_results = asyncio.run(_judge_debates(debates, args.judge_model))

    # Aggregate across all analysed debates.
    total_latching = 0
    total_disengaged = 0
    total_flipped = 0
    total_low_delta = 0
    total_low_delta_n = 0
    total_drift_judged = 0
    total_drifted = 0
    total_shape_fit = 0
    total_content_fit = 0

    for debate in debates:
        drift_obs = drift_results.get(debate.id)
        _print_debate_report(debate, drift=drift_obs)
        latching = analyse_latching(debate)
        total_latching += latching.n
        total_disengaged += sum(
            1 for o in latching.observations if o.classification == "disengaged_reaffirm"
        )
        total_flipped += sum(1 for o in latching.observations if o.classification == "flip")
        low_delta = analyse_low_delta_rounds(debate)
        total_low_delta += sum(1 for d in low_delta.deltas if d.is_low_delta)
        total_low_delta_n += low_delta.n
        if drift_obs is not None:
            total_drift_judged += 1
            if drift_obs.drift_flag:
                total_drifted += 1
            total_shape_fit += drift_obs.shape_fit
            total_content_fit += drift_obs.content_fit

    if len(debates) > 1:
        print(f"=== Aggregate across {len(debates)} debates ===")
        if total_latching:
            print(
                f"  Latching: {total_latching} observation(s) · "
                f"disengaged={total_disengaged / total_latching:.0%} · "
                f"flipped={total_flipped / total_latching:.0%}"
            )
        else:
            print("  Latching: no observations across the corpus")
        if total_low_delta_n:
            print(
                f"  Low-delta rounds: {total_low_delta / total_low_delta_n:.0%} of "
                f"{total_low_delta_n} elder-round comparisons"
            )
        if total_drift_judged:
            print(
                f"  Drift (LLM judge): {total_drifted}/{total_drift_judged} "
                f"drifted ({total_drifted / total_drift_judged:.0%}) · "
                f"avg shape_fit={total_shape_fit / total_drift_judged:.2f}/3 · "
                f"avg content_fit={total_content_fit / total_drift_judged:.2f}/3"
            )


if __name__ == "__main__":
    main()

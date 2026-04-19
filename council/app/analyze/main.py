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
import glob
from pathlib import Path

from council.adapters.storage.json_file import JsonFileStore
from council.domain.debate_analytics import (
    LatchingReport,
    LowDeltaReport,
    analyse_latching,
    analyse_low_delta_rounds,
)
from council.domain.models import Debate


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


def _print_debate_report(debate: Debate) -> None:
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

    print()


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
    args = parser.parse_args()

    debates = _load_debates(Path(args.store_root), args.target)
    if not debates:
        print("No debates found.")
        return

    # Aggregate across all analysed debates.
    total_latching = 0
    total_disengaged = 0
    total_flipped = 0
    total_low_delta = 0
    total_low_delta_n = 0

    for debate in debates:
        _print_debate_report(debate)
        latching = analyse_latching(debate)
        total_latching += latching.n
        total_disengaged += sum(
            1 for o in latching.observations if o.classification == "disengaged_reaffirm"
        )
        total_flipped += sum(1 for o in latching.observations if o.classification == "flip")
        low_delta = analyse_low_delta_rounds(debate)
        total_low_delta += sum(1 for d in low_delta.deltas if d.is_low_delta)
        total_low_delta_n += low_delta.n

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


if __name__ == "__main__":
    main()

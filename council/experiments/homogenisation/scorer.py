"""Phase 2 of the homogenisation probe: call the three judges per
debate, aggregate per-debate scores into per-roster summaries, write
scores.json.

Idempotent: if a scores.json already has an entry for a debate_id, the
entry is preserved and its judge calls are skipped on re-run.
"""

from __future__ import annotations

import json
import math
import os
import random
import statistics
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

from council.adapters.storage.json_file import JsonFileStore
from council.domain.models import Debate, ElderId
from council.domain.ports import ElderPort
from council.experiments.homogenisation.judges import (
    judge_best_r1,
    judge_claim_overlap,
    judge_preference,
)


@dataclass(frozen=True)
class DebateScoreRow:
    debate_id: str
    roster: str
    prompt_id: str
    r1_jaccard: float
    preference_winner: str  # "synthesis" | "best_r1" | "tie"


@dataclass(frozen=True)
class RosterSummary:
    roster: str
    n_debates: int
    mean_r1_jaccard: float
    median_r1_jaccard: float
    preference_rate: float
    preference_ci_lo: float
    preference_ci_hi: float


_ELDER_ORDER: tuple[ElderId, ElderId, ElderId] = ("claude", "gemini", "chatgpt")


def _r1_texts(debate: Debate) -> dict[ElderId, str]:
    if not debate.rounds:
        return {}
    r1 = debate.rounds[0]
    return {t.elder: (t.answer.text or "") for t in r1.turns}


async def _score_one_debate(
    debate: Debate, judge_port: ElderPort, rng: random.Random
) -> tuple[float, str]:
    """Run the three judges on one debate, return (r1_jaccard, winner)."""
    r1 = _r1_texts(debate)
    pairs = list(combinations(_ELDER_ORDER, 2))
    jaccards: list[float] = []
    for a, b in pairs:
        obs = await judge_claim_overlap(
            question=debate.prompt, answer_a=r1[a], answer_b=r1[b],
            judge_port=judge_port,
        )
        jaccards.append(obs.jaccard)
    mean_j = statistics.fmean(jaccards) if jaccards else 0.0

    answers = tuple(r1[e] for e in _ELDER_ORDER)
    best = await judge_best_r1(
        question=debate.prompt, answers=answers, judge_port=judge_port,
    )
    best_text = answers[best.best_index - 1]
    synth_text = debate.synthesis.text if debate.synthesis else ""
    pref = await judge_preference(
        question=debate.prompt, best_r1=best_text, synthesis=synth_text,
        judge_port=judge_port, rng=rng,
    )
    return mean_j, pref.winner


def _binomial_ci_90(*, successes: int, n: int) -> tuple[float, float]:
    """Wilson-approximation 90% CI for a binomial proportion.

    Uses the normal-approximation Wilson form; n=0 returns (0, 1).
    """
    if n == 0:
        return (0.0, 1.0)
    z = 1.6448536269514722  # 90% two-sided
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _write_scores(scores_path: Path, rows: list[dict[str, Any]]) -> None:
    """Atomic write of scores.json with fresh summaries from the given rows."""
    summaries = [asdict(s) for s in _summarise_rosters(rows)]
    scores_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = scores_path.with_suffix(scores_path.suffix + ".tmp")
    tmp.write_text(json.dumps({"rows": rows, "summaries": summaries}, indent=2))
    os.replace(tmp, scores_path)


def _summarise_rosters(rows: list[dict[str, Any]]) -> list[RosterSummary]:
    by_roster: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_roster.setdefault(r["roster"], []).append(r)
    out: list[RosterSummary] = []
    for name, group in sorted(by_roster.items()):
        jaccards = [g["r1_jaccard"] for g in group]
        # Synthesis wins count as 1, ties count as 0.5, losses 0.
        synth_score = sum(
            1.0 if g["preference_winner"] == "synthesis"
            else 0.5 if g["preference_winner"] == "tie" else 0.0
            for g in group
        )
        rate = synth_score / len(group) if group else 0.0
        # CI uses successes = round(synth_score), n = len(group) —
        # ties inflate the successes count by 0.5 which we round to
        # the nearest integer for the binomial approximation.
        successes = round(synth_score)
        lo, hi = _binomial_ci_90(successes=successes, n=len(group))
        out.append(RosterSummary(
            roster=name, n_debates=len(group),
            mean_r1_jaccard=statistics.fmean(jaccards) if jaccards else 0.0,
            median_r1_jaccard=statistics.median(jaccards) if jaccards else 0.0,
            preference_rate=rate, preference_ci_lo=lo, preference_ci_hi=hi,
        ))
    return out


async def score_probe(
    *,
    run_id: str,
    runs_root: Path,
    debate_store_root: Path,
    judge_port: ElderPort,
    seed: int = 0,
) -> Path:
    """Run judges across the manifest, aggregate, write scores.json."""
    manifest_path = runs_root / run_id / "manifest.json"
    scores_path = runs_root / run_id / "scores.json"
    manifest = json.loads(manifest_path.read_text())
    existing: dict[str, dict[str, Any]] = {}
    if scores_path.exists():
        data = json.loads(scores_path.read_text())
        existing = {r["debate_id"]: r for r in data.get("rows", [])}
    store = JsonFileStore(root=debate_store_root)
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    for entry in manifest["entries"]:
        debate_id = entry["debate_id"]
        if debate_id in existing:
            rows.append(existing[debate_id])
            _write_scores(scores_path, rows)
            continue
        debate = store.load(debate_id)
        r1_jaccard, winner = await _score_one_debate(debate, judge_port, rng)
        row = DebateScoreRow(
            debate_id=debate_id,
            roster=entry["roster"],
            prompt_id=entry["prompt_id"],
            r1_jaccard=r1_jaccard,
            preference_winner=winner,
        )
        rows.append(asdict(row))
        _write_scores(scores_path, rows)
    # Ensure at least one write happens even if manifest is empty:
    if not manifest["entries"]:
        _write_scores(scores_path, rows)
    return scores_path

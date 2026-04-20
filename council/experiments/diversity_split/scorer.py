"""Phase 2 of the diversity_split experiment: multi-judge scoring.

Mirrors ``council.experiments.homogenisation.scorer`` but routes the
preference rubric through ``judge_preference_multi`` so every
per-debate row carries the verdict from each of N judges plus a
majority aggregate.

Rationale: the 2026-04-20 judge-swap replication showed single-judge
preference verdicts are judge-family-biased. Under the Stage 11 spec
(``docs/superpowers/specs/2026-04-20-stage-11-diversity-split-design.md``)
preference must be multi-judge from the start. Claim-overlap and
best-R1 stay single-judge; they're mechanically less preference-sensitive
and this keeps costs bounded.

Output shape matches the homogenisation scorer for direct comparison:
``scores.json`` has top-level ``rows`` and ``summaries``. Each row
gains a ``judge_verdicts`` list (one entry per judge) and a
``preference_unanimous`` flag; ``preference_winner`` carries the
majority aggregate.
"""

from __future__ import annotations

import json
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
from council.domain.preference import judge_preference_multi
from council.domain.synthesis_output import parse_synthesis
from council.experiments.homogenisation.judges import judge_best_r1, judge_claim_overlap
from council.experiments.homogenisation.scorer import _binomial_ci_90


@dataclass(frozen=True)
class DebateScoreRow:
    debate_id: str
    roster: str
    prompt_id: str
    r1_jaccard: float
    preference_winner: str  # majority aggregate: "synthesis" | "best_r1" | "tie"
    preference_unanimous: bool
    judge_verdicts: list[dict[str, str]]  # [{judge_model, winner, reason}, ...]


@dataclass(frozen=True)
class RosterSummary:
    roster: str
    n_debates: int
    mean_r1_jaccard: float
    median_r1_jaccard: float
    preference_rate: float
    preference_ci_lo: float
    preference_ci_hi: float


_ELDER_ORDER: tuple[ElderId, ElderId, ElderId] = ("ada", "kai", "mei")


def _r1_texts(debate: Debate) -> dict[ElderId, str]:
    if not debate.rounds:
        return {}
    r1 = debate.rounds[0]
    return {t.elder: (t.answer.text or "") for t in r1.turns}


async def _score_one_debate(
    debate: Debate,
    *,
    single_judge: ElderPort,
    preference_judges: list[tuple[str, ElderPort]],
    rng: random.Random,
) -> tuple[float, str, bool, list[dict[str, str]]]:
    """Score one debate. Returns (r1_jaccard, aggregate_winner,
    unanimous, per-judge verdict dicts).

    ``single_judge`` handles the 3 pairwise claim-overlap calls plus the
    best-R1 pick (both are cost-sensitive and less preference-biased).
    ``preference_judges`` all vote on the synthesis-vs-best-R1 preference.
    """
    r1 = _r1_texts(debate)
    pairs = list(combinations(_ELDER_ORDER, 2))
    jaccards: list[float] = []
    for a, b in pairs:
        obs = await judge_claim_overlap(
            question=debate.prompt,
            answer_a=r1[a],
            answer_b=r1[b],
            judge_port=single_judge,
        )
        jaccards.append(obs.jaccard)
    mean_j = statistics.fmean(jaccards) if jaccards else 0.0

    answers = tuple(r1[e] for e in _ELDER_ORDER)
    best = await judge_best_r1(
        question=debate.prompt,
        answers=answers,
        judge_port=single_judge,
    )
    best_text = answers[best.best_index - 1]
    # BUG FIX 2026-04-20: the preference judge used to receive the raw
    # synthesis text including the ANSWER:/WHY:/DISAGREEMENTS: structural
    # labels, which the user never sees. The judge's rubric penalises
    # bloat and shape-fit, so synthesis was being systematically
    # handicapped for a wrapper the deliverable doesn't actually include.
    # Parse the synthesis and send only the ANSWER body — what
    # run_headless actually shows to the user.
    raw_synth = debate.synthesis.text if debate.synthesis else ""
    synth_text = parse_synthesis(raw_synth).answer if raw_synth else ""

    multi = await judge_preference_multi(
        question=debate.prompt,
        synthesis=synth_text,
        best_r1=best_text,
        judges=preference_judges,
        rng=rng,
    )
    verdicts = [
        {
            "judge_model": jv.judge_model,
            "winner": jv.verdict.winner,
            "reason": jv.verdict.reason,
        }
        for jv in multi.verdicts
    ]
    return mean_j, multi.aggregate, multi.unanimous, verdicts


def _write_scores(scores_path: Path, rows: list[dict[str, Any]]) -> None:
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
        synth_score = sum(
            1.0
            if g["preference_winner"] == "synthesis"
            else 0.5
            if g["preference_winner"] == "tie"
            else 0.0
            for g in group
        )
        rate = synth_score / len(group) if group else 0.0
        successes = round(synth_score)
        lo, hi = _binomial_ci_90(successes=successes, n=len(group))
        out.append(
            RosterSummary(
                roster=name,
                n_debates=len(group),
                mean_r1_jaccard=statistics.fmean(jaccards) if jaccards else 0.0,
                median_r1_jaccard=statistics.median(jaccards) if jaccards else 0.0,
                preference_rate=rate,
                preference_ci_lo=lo,
                preference_ci_hi=hi,
            )
        )
    return out


async def score_probe_multi(
    *,
    run_id: str,
    runs_root: Path,
    debate_store_root: Path,
    single_judge: ElderPort,
    preference_judges: list[tuple[str, ElderPort]],
    seed: int = 0,
) -> Path:
    """Run single-judge claim-overlap/best-R1 and multi-judge preference
    across a manifest, aggregate, write scores.json.

    Idempotent: preserves existing rows for debates already scored.
    """
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
        jaccard, winner, unanimous, verdicts = await _score_one_debate(
            debate,
            single_judge=single_judge,
            preference_judges=preference_judges,
            rng=rng,
        )
        row = DebateScoreRow(
            debate_id=debate_id,
            roster=entry["roster"],
            prompt_id=entry["prompt_id"],
            r1_jaccard=jaccard,
            preference_winner=winner,
            preference_unanimous=unanimous,
            judge_verdicts=verdicts,
        )
        rows.append(asdict(row))
        _write_scores(scores_path, rows)
    if not manifest["entries"]:
        _write_scores(scores_path, rows)
    return scores_path

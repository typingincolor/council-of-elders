"""Per-debate run summary — the observability artifact for every run.

Every debate produces one JSON sidecar file that records how the
diversity-engine decided to handle it and how the deliverable compared
against the best-R1 baseline. This is the artifact that makes each run
'teach you something' — the single source of truth for: was the
diversity classification correct? Did the policy pick the right mode?
Did the synthesis beat best-R1?

Stored as ``<reports-root>/<debate-id>-summary.json``.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from council.domain.debate_policy import DebatePolicy
from council.domain.diversity import DiversityScore
from council.domain.models import Debate, ElderId
from council.domain.preference import PreferenceVerdict
from council.domain.roster import RosterSpec
from council.domain.synthesis_output import SynthesisOutput


@dataclass(frozen=True)
class RunSummary:
    debate_id: str
    prompt: str
    roster: dict[str, Any]
    diversity: dict[str, Any]
    policy: dict[str, Any]
    rounds_executed: int
    best_r1_elder: ElderId | None
    synthesis_generated: bool
    synthesis_structured: dict[str, Any] | None
    preference: dict[str, Any] | None


def build_run_summary(
    *,
    debate: Debate,
    roster_spec: RosterSpec | None,
    diversity: DiversityScore | None,
    policy: DebatePolicy,
    synthesis: SynthesisOutput | None,
    preference: PreferenceVerdict | None,
) -> RunSummary:
    roster_payload: dict[str, Any] = (
        {"name": roster_spec.name, "models": dict(roster_spec.models)}
        if roster_spec is not None
        else {"name": "unknown", "models": {}}
    )
    diversity_payload: dict[str, Any] = (
        {
            "classification": diversity.classification,
            "provider_count": diversity.provider_count,
            "identical_model_count": diversity.identical_model_count,
            "flags": list(diversity.flags),
            "rationale": diversity.rationale,
        }
        if diversity is not None
        else {"classification": "unknown", "rationale": "no roster spec available"}
    )
    policy_payload = {
        "mode": policy.mode,
        "max_rounds": policy.max_rounds,
        "synthesise": policy.synthesise,
        "always_compute_best_r1": policy.always_compute_best_r1,
        "warning": policy.warning,
    }
    synth_payload: dict[str, Any] | None = None
    if synthesis is not None:
        synth_payload = {
            "answer": synthesis.answer,
            "why": synthesis.why,
            "disagreements": list(synthesis.disagreements),
        }
    preference_payload: dict[str, Any] | None = None
    if preference is not None:
        preference_payload = {
            "winner": preference.winner,
            "reason": preference.reason,
        }
    return RunSummary(
        debate_id=debate.id,
        prompt=debate.prompt,
        roster=roster_payload,
        diversity=diversity_payload,
        policy=policy_payload,
        rounds_executed=len(debate.rounds),
        best_r1_elder=debate.best_r1_elder,
        synthesis_generated=synth_payload is not None,
        synthesis_structured=synth_payload,
        preference=preference_payload,
    )


def write_run_summary(summary: RunSummary, *, root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{summary.debate_id}-summary.json"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(asdict(summary), indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path

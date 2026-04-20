"""Diversity scoring for a council roster.

Tier-1 heuristic: provider distinctness plus identical-model penalty.
Provider is inferred from the OpenRouter model-id prefix. Vendor-CLI
aliases (no slash, e.g. "sonnet") count as "unknown" — the heuristic is
only meaningful when OpenRouter is in use.

Treat as hypothesis-grade: the thresholds are directional, pulled from
the n=8 homogenisation probe
(`docs/experiments/2026-04-19-9288-homogenisation.md`). Calibration
against replicated probes with alternative judges is scaffolded
separately; until then, branch on this score as a warning signal, not
as settled truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from council.domain.roster import RosterSpec

DiversityClass = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class DiversityScore:
    classification: DiversityClass
    provider_count: int
    identical_model_count: int
    flags: tuple[str, ...]
    rationale: str


def provider_of(model_id: str) -> str:
    if "/" not in model_id:
        return "unknown"
    return model_id.split("/", 1)[0]


def score_roster(spec: RosterSpec) -> DiversityScore:
    models = list(spec.models.values())
    providers = {provider_of(m) for m in models}
    provider_count = len(providers)
    identical_model_count = sum(1 for m in models if models.count(m) > 1)
    all_identical = len(models) > 0 and len(set(models)) == 1

    flags: list[str] = []
    if identical_model_count >= 2:
        flags.append("identical_models")
    if provider_count == 1:
        flags.append("same_provider_trio")

    if all_identical or provider_count == 1:
        classification: DiversityClass = "low"
        flags.append("unsafe_consensus_risk")
        rationale = (
            f"{provider_count} distinct provider(s); all three slots share a "
            "provider family. Debate will iterate over a single perspective — "
            "prefer best-R1-first."
        )
    elif provider_count == 3 and identical_model_count == 0:
        classification = "high"
        rationale = (
            "Three distinct providers, no slot collisions — full debate is justified."
        )
    else:
        classification = "medium"
        bits: list[str] = []
        if provider_count == 2:
            bits.append("two distinct providers")
        if provider_count == 3 and identical_model_count >= 2:
            bits.append("three providers but duplicated model strings")
        rationale = (
            "; ".join(bits) + " — single critique round likely enough."
            if bits
            else "mixed lineage — single critique round likely enough."
        )

    return DiversityScore(
        classification=classification,
        provider_count=provider_count,
        identical_model_count=identical_model_count,
        flags=tuple(flags),
        rationale=rationale,
    )

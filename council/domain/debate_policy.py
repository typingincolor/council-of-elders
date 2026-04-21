"""Adaptive debate policy — maps a DiversityScore to a pipeline choice.

Low diversity → best-R1-first (warn, skip debate, skip synthesis).
Medium → R1 + one critique round + synthesis.
High → full debate + synthesis.

Best-R1 is always computed when a judge is available (mandatory
baseline, independent of policy). See
``docs/superpowers/plans/2026-04-20-diversity-engine-refactor.md``.

A fourth mode, ``r1_only``, is available as a user override only (never
auto-selected). It runs R1 then synthesises, skipping R2+. This is the
configuration the 2026-04-20 depth ablation and 2026-04-21 format
ablation found to be the strongest shape for this tool: debate rounds
were net-negative on synthesis quality for diverse rosters. Distinct
from ``best_r1_only`` which also skips R2+ but then skips synthesis too
(returns one of the three R1 answers verbatim).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from council.domain.diversity import DiversityScore

PolicyMode = Literal["best_r1_only", "r1_only", "single_critique", "full_debate"]


@dataclass(frozen=True)
class DebatePolicy:
    mode: PolicyMode
    max_rounds: int
    synthesise: bool
    always_compute_best_r1: bool
    warning: str | None


def policy_for(
    diversity: DiversityScore, *, user_override: DebatePolicy | None = None
) -> DebatePolicy:
    if user_override is not None:
        return user_override

    if diversity.classification == "low":
        return DebatePolicy(
            mode="best_r1_only",
            max_rounds=1,
            synthesise=False,
            always_compute_best_r1=True,
            warning=(
                "Low-diversity roster detected — degrading to best-R1-first "
                "(no debate, no synthesis). "
                f"Reason: {diversity.rationale}"
            ),
        )
    if diversity.classification == "medium":
        return DebatePolicy(
            mode="single_critique",
            max_rounds=2,
            synthesise=True,
            always_compute_best_r1=True,
            warning=None,
        )
    return DebatePolicy(
        mode="full_debate",
        max_rounds=6,
        synthesise=True,
        always_compute_best_r1=True,
        warning=None,
    )

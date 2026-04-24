from __future__ import annotations

from council.app.headless.printing import (
    print_best_r1_pick,
    print_best_r1_unavailable,
    print_max_rounds_exhausted,
)
from council.domain.best_r1 import LLMJudgedBestR1Selector
from council.domain.debate_policy import DebatePolicy, policy_for
from council.domain.debate_service import DebateService
from council.domain.diversity import score_roster
from council.domain.models import Debate
from council.domain.ports import ElderPort, TranscriptStore
from council.domain.roster import RosterSpec


def resolve_policy(
    *,
    user_override: DebatePolicy | None,
    roster_spec: RosterSpec | None,
    fallback_max_rounds: int,
) -> DebatePolicy:
    """Pick the effective policy.

    Priority: explicit user override > diversity-derived default > a
    conservative full-debate fallback (used when no roster spec is
    available, e.g. subprocess/CLI mode where model ids are unknown).
    """
    if user_override is not None:
        return user_override
    if roster_spec is not None and roster_spec.models:
        return policy_for(score_roster(roster_spec))
    return DebatePolicy(
        mode="full_debate",
        max_rounds=fallback_max_rounds,
        synthesise=True,
        always_compute_best_r1=True,
        warning=None,
    )


async def run_debate_rounds(
    *,
    debate: Debate,
    svc: DebateService,
    policy: DebatePolicy,
) -> None:
    """Execute rounds under the given policy.

    R1 always runs. R2 runs for every mode except best_r1_only/r1_only.
    full_debate then continues R3+ until convergence or max_rounds.
    """
    await svc.run_round(debate)
    if policy.mode in ("best_r1_only", "r1_only"):
        return

    await svc.run_round(debate)
    if policy.mode != "full_debate":
        return

    while len(debate.rounds) < policy.max_rounds and not svc.rules.is_converged(debate.rounds[-1]):
        await svc.run_round(debate)
    if len(debate.rounds) >= policy.max_rounds and not svc.rules.is_converged(debate.rounds[-1]):
        print_max_rounds_exhausted(policy.max_rounds)


async def select_best_r1(
    *,
    debate: Debate,
    store: TranscriptStore,
    best_r1_judge: ElderPort | None,
) -> str | None:
    """Judge-pick the strongest R1 answer, record it on the debate, return its text.

    Subprocess mode has no cheap judge — prints a notice and skips.
    """
    if best_r1_judge is None:
        print_best_r1_unavailable()
        return None

    pick = await LLMJudgedBestR1Selector(judge_port=best_r1_judge).select(debate)
    if pick is None:
        return None

    debate.best_r1_elder = pick.elder
    store.save(debate)
    best_r1_text = next(
        (t.answer.text for t in debate.rounds[0].turns if t.elder == pick.elder),
        None,
    )
    print_best_r1_pick(pick.elder, pick.reason)
    return best_r1_text

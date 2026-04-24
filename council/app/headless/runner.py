from __future__ import annotations

import dataclasses
import uuid
from pathlib import Path

from council.domain.best_r1 import LLMJudgedBestR1Selector
from council.domain.debate_policy import DebatePolicy, policy_for
from council.domain.debate_service import DebateService
from council.domain.diversity import DiversityScore, score_roster
from council.domain.models import CouncilPack, Debate, ElderId
from council.domain.ports import Clock, ElderPort, EventBus, TranscriptStore
from council.domain.preference import (
    MultiJudgeVerdict,
    PreferenceVerdict,
    judge_preference,
    judge_preference_multi,
)
from council.domain.roster import RosterSpec
from council.domain.run_summary import build_run_summary, write_run_summary
from council.domain.synthesis_output import SynthesisOutput, parse_synthesis

_LABELS: dict[ElderId, str] = {
    "ada": "Ada",
    "kai": "Kai",
    "mei": "Mei",
}


def _resolve_policy(
    *,
    user_override: DebatePolicy | None,
    roster_spec: RosterSpec | None,
    fallback_max_rounds: int,
) -> DebatePolicy:
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


async def _run_debate_rounds(*, debate: Debate, svc: DebateService, policy: DebatePolicy) -> None:
    await svc.run_round(debate)

    if policy.mode in ("best_r1_only", "r1_only"):
        return

    await svc.run_round(debate)

    if policy.mode != "full_debate":
        return

    while len(debate.rounds) < policy.max_rounds and not svc.rules.is_converged(debate.rounds[-1]):
        await svc.run_round(debate)
    if len(debate.rounds) >= policy.max_rounds and not svc.rules.is_converged(debate.rounds[-1]):
        print(
            f"[warning] Hit policy max_rounds={policy.max_rounds} "
            "without full convergence. Synthesising best-effort."
        )


def _print_rounds(debate: Debate) -> None:
    for rnd in debate.rounds:
        print(f"--- Round {rnd.number} ---")
        for turn in rnd.turns:
            label = _LABELS[turn.elder]
            if turn.answer.error:
                print(f"[{label}] ERROR {turn.answer.error.kind}: {turn.answer.error.detail}\n")
            else:
                print(f"[{label}] {turn.answer.text}\n")


async def _select_best_r1(
    *,
    debate: Debate,
    store: TranscriptStore,
    best_r1_judge: ElderPort | None,
) -> str | None:
    if best_r1_judge is None:
        print("\n[Best-R1 baseline unavailable (no OpenRouter judge configured).]\n")
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
    print(f"\n[Best R1 (judge-picked): {_LABELS[pick.elder]}] {pick.reason}\n")
    return best_r1_text


def _synthesis_risk_note(
    *,
    policy: DebatePolicy,
    roster_spec: RosterSpec | None,
) -> str | None:
    if not policy.synthesise or roster_spec is None or not roster_spec.models:
        return None
    # Risk disclosure rationale: under the 2026-04-19 probe and its
    # 2026-04-20 judge-swap replication, synthesis rarely beat the
    # strongest individual R1 answer on low/medium-diversity rosters.
    # We surface this note so users compare outputs rather than trusting
    # synthesis blindly in those conditions.
    div = score_roster(roster_spec)
    if div.classification in ("low", "medium"):
        return (
            f"[note] In {div.classification}-diversity runs, synthesis "
            "historically rarely outperforms the strongest individual "
            "answer. Both are shown — inspect both before acting."
        )
    return None


async def run_headless(
    prompt: str,
    pack: CouncilPack,
    elders: dict[ElderId, ElderPort],
    store: TranscriptStore,
    clock: Clock,
    bus: EventBus,
    synthesizer: ElderId,
    *,
    using_openrouter: bool = False,
    max_rounds: int = 3,
    report_store=None,  # ReportFileStore | None
    best_r1_judge: ElderPort | None = None,
    preference_judge: ElderPort | None = None,
    preference_judges: list[tuple[str, ElderPort]] | None = None,
    policy: DebatePolicy | None = None,
    roster_spec: RosterSpec | None = None,
    run_summary_root: Path | None = None,
    synthesise_override: bool | None = None,
) -> None:
    if max_rounds < 2:
        raise ValueError("max_rounds must be at least 2 (R1+R2 are mandatory)")

    effective_policy = _resolve_policy(
        user_override=policy,
        roster_spec=roster_spec,
        fallback_max_rounds=max_rounds,
    )

    if synthesise_override is not None:
        effective_policy = dataclasses.replace(effective_policy, synthesise=synthesise_override)

    if effective_policy.warning:
        print(f"[warning] {effective_policy.warning}")

    debate = Debate(
        id=str(uuid.uuid4()),
        prompt=prompt,
        pack=pack,
        rounds=[],
        status="in_progress",
        synthesis=None,
    )
    svc = DebateService(elders=elders, store=store, clock=clock, bus=bus)
    await _run_debate_rounds(debate=debate, svc=svc, policy=effective_policy)
    _print_rounds(debate)
    best_r1_text = await _select_best_r1(
        debate=debate,
        store=store,
        best_r1_judge=best_r1_judge,
    )

    structured: SynthesisOutput | None = None
    preference: PreferenceVerdict | MultiJudgeVerdict | None = None
    synthesis_risk_note = _synthesis_risk_note(policy=effective_policy, roster_spec=roster_spec)

    if effective_policy.synthesise:
        synth = await svc.synthesize(debate, by=synthesizer)
        structured = parse_synthesis(synth.text or "")
        print(f"\n[Synthesis by {_LABELS[synthesizer]}]\n")
        if synthesis_risk_note:
            print(f"{synthesis_risk_note}\n")
        print(structured.answer)
        if structured.why:
            print(f"\nWhy: {structured.why}")
        if structured.disagreements:
            print("\nDisagreements:")
            for d in structured.disagreements:
                print(f"- {d}")
        else:
            print("\nDisagreements: none material.")

        if best_r1_text and structured.answer:
            # Preference judge(s): synthesis vs best-R1 — answers the core
            # success-signal question. Multi-judge is preferred because
            # 2026-04-20 showed single-judge preference verdicts can be
            # judge-family biased.
            if preference_judges:
                preference = await judge_preference_multi(
                    question=prompt,
                    synthesis=structured.answer,
                    best_r1=best_r1_text,
                    judges=preference_judges,
                )
                print(
                    f"\n[Preference judges] aggregate={preference.aggregate} "
                    f"(unanimous={preference.unanimous}, "
                    f"n_judges={len(preference.verdicts)})"
                )
                for jv in preference.verdicts:
                    print(f"  · {jv.judge_model}: {jv.verdict.winner} — {jv.verdict.reason}")
            elif preference_judge is not None:
                preference = await judge_preference(
                    question=prompt,
                    synthesis=structured.answer,
                    best_r1=best_r1_text,
                    judge_port=preference_judge,
                )
                print(f"\n[Preference judge] {preference.winner} — {preference.reason}")

        try:
            report_md = await svc.generate_report(
                debate, by=synthesizer, synthesis_risk_note=synthesis_risk_note
            )
            print("\n--- Debate report ---\n")
            print(report_md)
            if report_store is not None:
                path = report_store.save(debate_id=debate.id, markdown=report_md)
                print(f"\nReport saved to {path}")
        except Exception as ex:
            print(f"\n[warning] Report generation failed: {ex}")
    else:
        if debate.best_r1_elder is not None and best_r1_text:
            print(f"[Answer (best-R1, {_LABELS[debate.best_r1_elder]})] {best_r1_text}")
        else:
            print("[warning] best-R1-only mode but no judge available — no deliverable produced.")

    if run_summary_root is not None:
        diversity: DiversityScore | None = (
            score_roster(roster_spec) if roster_spec is not None and roster_spec.models else None
        )
        preference_judge_model: str | None = None
        if isinstance(preference, PreferenceVerdict) and preference_judge is not None:
            preference_judge_model = getattr(preference_judge, "model", None)
        summary = build_run_summary(
            debate=debate,
            roster_spec=roster_spec,
            diversity=diversity,
            policy=effective_policy,
            synthesis=structured,
            preference=preference,
            preference_judge_model=preference_judge_model,
        )
        summary_path = write_run_summary(summary, root=run_summary_root)
        print(f"\n[run summary] {summary_path}")

    if using_openrouter:
        from council.adapters.elders.openrouter import (
            OpenRouterAdapter,
            format_cost_notice,
        )

        any_or = next(
            (e for e in elders.values() if isinstance(e, OpenRouterAdapter)),
            None,
        )
        used, limit = (0.0, None)
        if any_or is not None:
            used, limit = await any_or.fetch_credits()
        total = sum(e.session_cost_usd for e in elders.values() if isinstance(e, OpenRouterAdapter))
        line = format_cost_notice(
            elders=elders,
            round_cost_delta_usd=total,
            credits_used=used,
            credits_limit=limit,
        )
        print(line)

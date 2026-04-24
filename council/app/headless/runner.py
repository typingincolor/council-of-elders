from __future__ import annotations

import dataclasses
import uuid
from pathlib import Path

from council.app.headless.printing import (
    print_best_r1_only_deliverable,
    print_policy_warning,
    print_preference,
    print_rounds,
    print_synthesis,
)
from council.app.headless.reporting import (
    emit_openrouter_cost_notice,
    generate_and_save_report,
    judge_preference_verdict,
    run_synthesis,
    synthesis_risk_note,
    write_summary_sidecar,
)
from council.app.headless.rounds import (
    resolve_policy,
    run_debate_rounds,
    select_best_r1,
)
from council.domain.debate_policy import DebatePolicy
from council.domain.debate_service import DebateService
from council.domain.models import CouncilPack, Debate, ElderId
from council.domain.ports import Clock, ElderPort, EventBus, TranscriptStore
from council.domain.preference import MultiJudgeVerdict, PreferenceVerdict
from council.domain.roster import RosterSpec
from council.domain.synthesis_output import SynthesisOutput


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
    """Headless one-shot debate.

    Under the adaptive policy: low-diversity rosters skip debate and
    skip synthesis (best-R1-only); medium run R1+R2 + synthesis; high
    run full debate + synthesis. ``max_rounds`` is only consulted as
    the fallback when no policy and no roster_spec is supplied.
    """
    if max_rounds < 2:
        raise ValueError("max_rounds must be at least 2 (R1+R2 are mandatory)")

    effective_policy = resolve_policy(
        user_override=policy,
        roster_spec=roster_spec,
        fallback_max_rounds=max_rounds,
    )
    # --synthesise / --no-synthesise composes with the policy: e.g.
    # full_debate --no-synthesise runs the whole debate and stops;
    # best_r1_only --synthesise is effectively r1_only.
    if synthesise_override is not None:
        effective_policy = dataclasses.replace(effective_policy, synthesise=synthesise_override)
    if effective_policy.warning:
        print_policy_warning(effective_policy.warning)

    debate = Debate(
        id=str(uuid.uuid4()),
        prompt=prompt,
        pack=pack,
        rounds=[],
        status="in_progress",
        synthesis=None,
    )
    svc = DebateService(elders=elders, store=store, clock=clock, bus=bus)

    await run_debate_rounds(debate=debate, svc=svc, policy=effective_policy)
    print_rounds(debate)
    best_r1_text = await select_best_r1(
        debate=debate,
        store=store,
        best_r1_judge=best_r1_judge,
    )

    structured: SynthesisOutput | None = None
    preference: PreferenceVerdict | MultiJudgeVerdict | None = None
    risk_note = synthesis_risk_note(policy=effective_policy, roster_spec=roster_spec)

    if effective_policy.synthesise:
        structured = await run_synthesis(svc=svc, debate=debate, synthesizer=synthesizer)
        print_synthesis(structured=structured, synthesizer=synthesizer, risk_note=risk_note)
        if best_r1_text and structured.answer:
            preference = await judge_preference_verdict(
                prompt=prompt,
                synthesis_answer=structured.answer,
                best_r1_text=best_r1_text,
                preference_judge=preference_judge,
                preference_judges=preference_judges,
            )
            if preference is not None:
                print_preference(preference)
        await generate_and_save_report(
            svc=svc,
            debate=debate,
            synthesizer=synthesizer,
            risk_note=risk_note,
            report_store=report_store,
        )
    else:
        print_best_r1_only_deliverable(debate, best_r1_text)

    if run_summary_root is not None:
        write_summary_sidecar(
            debate=debate,
            roster_spec=roster_spec,
            policy=effective_policy,
            structured=structured,
            preference=preference,
            preference_judge=preference_judge,
            root=run_summary_root,
        )

    if using_openrouter:
        await emit_openrouter_cost_notice(elders)

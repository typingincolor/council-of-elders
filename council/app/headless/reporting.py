from __future__ import annotations

from pathlib import Path

from council.app.headless.printing import (
    print_report,
    print_report_failed,
    print_run_summary_path,
)
from council.domain.debate_policy import DebatePolicy
from council.domain.debate_service import DebateService
from council.domain.diversity import DiversityScore, score_roster
from council.domain.models import Debate, ElderId
from council.domain.ports import ElderPort
from council.domain.preference import (
    MultiJudgeVerdict,
    PreferenceVerdict,
    judge_preference,
    judge_preference_multi,
)
from council.domain.roster import RosterSpec
from council.domain.run_summary import build_run_summary, write_run_summary
from council.domain.synthesis_output import SynthesisOutput, parse_synthesis


def synthesis_risk_note(
    *,
    policy: DebatePolicy,
    roster_spec: RosterSpec | None,
) -> str | None:
    """Surface the "synthesis rarely wins on low/medium diversity" warning.

    Rationale: under the 2026-04-19 probe and its 2026-04-20 judge-swap
    replication, synthesis rarely beat the strongest individual R1 answer
    on low/medium-diversity rosters. We surface this so users compare
    outputs rather than trusting synthesis blindly. High-diversity: omit
    (evidence is ambiguous). No roster_spec: omit (we don't know).
    """
    if not policy.synthesise or roster_spec is None or not roster_spec.models:
        return None
    div = score_roster(roster_spec)
    if div.classification in ("low", "medium"):
        return (
            f"[note] In {div.classification}-diversity runs, synthesis "
            "historically rarely outperforms the strongest individual "
            "answer. Both are shown — inspect both before acting."
        )
    return None


async def run_synthesis(
    *,
    svc: DebateService,
    debate: Debate,
    synthesizer: ElderId,
) -> SynthesisOutput:
    synth = await svc.synthesize(debate, by=synthesizer)
    return parse_synthesis(synth.text or "")


async def judge_preference_verdict(
    *,
    prompt: str,
    synthesis_answer: str,
    best_r1_text: str,
    preference_judge: ElderPort | None,
    preference_judges: list[tuple[str, ElderPort]] | None,
) -> PreferenceVerdict | MultiJudgeVerdict | None:
    """Resolve synthesis-vs-best-R1 preference.

    Multi-judge is preferred: 2026-04-20 showed single-judge preference
    verdicts can be judge-family biased. ``preference_judges`` takes
    precedence over the legacy single ``preference_judge`` kwarg.
    """
    if preference_judges:
        return await judge_preference_multi(
            question=prompt,
            synthesis=synthesis_answer,
            best_r1=best_r1_text,
            judges=preference_judges,
        )
    if preference_judge is not None:
        return await judge_preference(
            question=prompt,
            synthesis=synthesis_answer,
            best_r1=best_r1_text,
            judge_port=preference_judge,
        )
    return None


async def generate_and_save_report(
    *,
    svc: DebateService,
    debate: Debate,
    synthesizer: ElderId,
    risk_note: str | None,
    report_store,  # ReportFileStore | None
) -> None:
    try:
        report_md = await svc.generate_report(
            debate, by=synthesizer, synthesis_risk_note=risk_note
        )
    except Exception as ex:
        print_report_failed(ex)
        return
    saved_to: Path | None = None
    if report_store is not None:
        saved_to = report_store.save(debate_id=debate.id, markdown=report_md)
    print_report(report_md, saved_to=saved_to)


def write_summary_sidecar(
    *,
    debate: Debate,
    roster_spec: RosterSpec | None,
    policy: DebatePolicy,
    structured: SynthesisOutput | None,
    preference: PreferenceVerdict | MultiJudgeVerdict | None,
    preference_judge: ElderPort | None,
    root: Path,
) -> None:
    diversity: DiversityScore | None = (
        score_roster(roster_spec) if roster_spec is not None and roster_spec.models else None
    )
    # Record single-judge model id so single-verdict preference payloads
    # carry judge provenance. Multi-judge payloads already embed the
    # model ids inside their verdicts list.
    preference_judge_model: str | None = None
    if isinstance(preference, PreferenceVerdict) and preference_judge is not None:
        preference_judge_model = getattr(preference_judge, "model", None)
    summary = build_run_summary(
        debate=debate,
        roster_spec=roster_spec,
        diversity=diversity,
        policy=policy,
        synthesis=structured,
        preference=preference,
        preference_judge_model=preference_judge_model,
    )
    path = write_run_summary(summary, root=root)
    print_run_summary_path(path)


async def emit_openrouter_cost_notice(elders: dict[ElderId, ElderPort]) -> None:
    from council.adapters.elders.openrouter import OpenRouterAdapter, format_cost_notice

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
        # Headless is a one-shot session — the "round delta" is the whole session.
        round_cost_delta_usd=total,
        credits_used=used,
        credits_limit=limit,
    )
    print(line)

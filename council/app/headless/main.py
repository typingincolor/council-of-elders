from __future__ import annotations

import argparse
import asyncio
import dataclasses
import uuid
from pathlib import Path

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.system import SystemClock
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.json_file import JsonFileStore
from council.app.bootstrap import build_elders
from council.app.config import load_config
from council.domain.best_r1 import LLMJudgedBestR1Selector
from council.domain.debate_policy import DebatePolicy, PolicyMode, policy_for
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
    """Pick the effective policy for this run.

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

    effective_policy = _resolve_policy(
        user_override=policy,
        roster_spec=roster_spec,
        fallback_max_rounds=max_rounds,
    )

    # Explicit --synthesise / --no-synthesise overrides the policy's
    # built-in choice. Composes with every mode — e.g. full_debate
    # --no-synthesise runs the whole debate then stops; best_r1_only
    # --synthesise is effectively r1_only.
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

    # Always run R1 — every pipeline mode needs initial answers.
    await svc.run_round(debate)

    if effective_policy.mode not in ("best_r1_only", "r1_only"):
        # R2 is the cross-examination round; every non-skip mode uses it.
        await svc.run_round(debate)
        if effective_policy.mode == "full_debate":
            # R3+ until policy budget spent or elders converge early.
            while len(debate.rounds) < effective_policy.max_rounds and not svc.rules.is_converged(
                debate.rounds[-1]
            ):
                await svc.run_round(debate)
            if len(debate.rounds) >= effective_policy.max_rounds and not svc.rules.is_converged(
                debate.rounds[-1]
            ):
                print(
                    f"[warning] Hit policy max_rounds={effective_policy.max_rounds} "
                    "without full convergence. Synthesising best-effort."
                )

    # Print each round's turns in order.
    for r in debate.rounds:
        print(f"--- Round {r.number} ---")
        for t in r.turns:
            label = _LABELS[t.elder]
            if t.answer.error:
                print(f"[{label}] ERROR {t.answer.error.kind}: {t.answer.error.detail}\n")
            else:
                print(f"[{label}] {t.answer.text}\n")

    # Best-R1 baseline — mandatory comparison point against synthesis.
    # Only runs when a judge is wired in (OpenRouter path); subprocess mode
    # prints a notice and skips, since we have no cheap judge available.
    best_r1_text: str | None = None
    if best_r1_judge is not None:
        pick = await LLMJudgedBestR1Selector(judge_port=best_r1_judge).select(debate)
        if pick is not None:
            debate.best_r1_elder = pick.elder
            store.save(debate)
            best_r1_text = next(
                (t.answer.text for t in debate.rounds[0].turns if t.elder == pick.elder),
                None,
            )
            print(f"\n[Best R1 (judge-picked): {_LABELS[pick.elder]}] {pick.reason}\n")
    else:
        print("\n[Best-R1 baseline unavailable (no OpenRouter judge configured).]\n")

    structured: SynthesisOutput | None = None
    preference: PreferenceVerdict | MultiJudgeVerdict | None = None

    # Risk disclosure: under the 2026-04-19 probe and its 2026-04-20
    # judge-swap replication, synthesis rarely beats the best individual
    # R1 answer on low- or medium-diversity rosters. Flag that here so
    # the reader is prompted to compare instead of trusting synthesis
    # blindly. Omitted on high diversity, where the evidence is
    # ambiguous rather than negative. Also omitted when we don't know
    # the diversity (no roster_spec supplied).
    synthesis_risk_note: str | None = None
    if effective_policy.synthesise and roster_spec is not None and roster_spec.models:
        div = score_roster(roster_spec)
        if div.classification in ("low", "medium"):
            synthesis_risk_note = (
                f"[note] In {div.classification}-diversity runs, synthesis "
                "historically rarely outperforms the strongest individual "
                "answer. Both are shown — inspect both before acting."
            )

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

        # Preference judge(s): synthesis vs best-R1 — answers the core
        # success-signal question. Multi-judge is the preferred shape
        # under the diversity-engine direction (see
        # docs/experiments/2026-04-20-judge-replication.md for why
        # single-judge preference verdicts are judge-family-biased).
        # preference_judges takes precedence over the legacy single
        # preference_judge kwarg.
        if best_r1_text and structured.answer:
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

        # Generate the debate report and print + optionally save it.
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
        # best-R1-only mode: emit the judge-picked answer as the deliverable.
        if debate.best_r1_elder is not None and best_r1_text:
            print(f"[Answer (best-R1, {_LABELS[debate.best_r1_elder]})] {best_r1_text}")
        else:
            print("[warning] best-R1-only mode but no judge available — no deliverable produced.")

    # Emit the observability sidecar. Captures roster, diversity, policy,
    # rounds, best-R1 pick, structured synthesis, and preference verdict.
    if run_summary_root is not None:
        diversity: DiversityScore | None = (
            score_roster(roster_spec) if roster_spec is not None and roster_spec.models else None
        )
        # When the caller used the single preference_judge fallback,
        # record its model id so the emitted (single-verdict) preference
        # payload carries judge provenance. Multi-judge payloads already
        # embed each judge's model id inside the verdicts list.
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
            round_cost_delta_usd=total,  # for headless a single "round" = whole session
            credits_used=used,
            credits_limit=limit,
        )
        print(line)


def _max_rounds_type(value: str) -> int:
    n = int(value)
    if n < 2:
        raise argparse.ArgumentTypeError("--max-rounds must be at least 2 (R1+R2 are mandatory)")
    return n


def _policy_override_from_args(mode: str, max_rounds: int) -> DebatePolicy | None:
    if mode == "auto":
        return None
    pm: PolicyMode = mode  # type: ignore[assignment]
    # r1_only: R1 then synthesise, skip R2+. Experimentally the strongest
    # shape for diverse rosters (see 2026-04-20-226f, 2026-04-21-f13d).
    return DebatePolicy(
        mode=pm,
        max_rounds=max_rounds
        if mode == "full_debate"
        else {"best_r1_only": 1, "r1_only": 1, "single_critique": 2}[mode],
        synthesise=mode != "best_r1_only",
        always_compute_best_r1=True,
        warning=None,
    )


def main() -> None:
    import os

    parser = argparse.ArgumentParser(prog="council-headless")
    parser.add_argument("prompt")
    parser.add_argument("--pack", default="bare")
    parser.add_argument("--packs-root", default=str(Path.home() / ".council" / "packs"))
    parser.add_argument("--synthesizer", choices=["ada", "kai", "mei"], default="ada")
    parser.add_argument("--store-root", default=str(Path.home() / ".council" / "debates"))
    parser.add_argument(
        "--claude-model",
        default=os.environ.get("COUNCIL_CLAUDE_MODEL"),
        help="Model alias or full name passed to `claude --model` (e.g. sonnet, opus).",
    )
    parser.add_argument(
        "--gemini-model",
        default=os.environ.get("COUNCIL_GEMINI_MODEL"),
        help="Model name passed to `gemini -m` (e.g. gemini-2.5-flash — recommended; Pro has tight quota).",
    )
    parser.add_argument(
        "--codex-model",
        default=os.environ.get("COUNCIL_CODEX_MODEL"),
        help="Model name passed to `codex exec -m` (e.g. gpt-5-codex).",
    )
    parser.add_argument(
        "--max-rounds",
        type=_max_rounds_type,
        default=6,
        help=(
            "Upper bound on rounds for full_debate mode. Ignored in other "
            "policy modes. Minimum 2; default 6."
        ),
    )
    parser.add_argument(
        "--policy",
        choices=["auto", "best_r1_only", "r1_only", "single_critique", "full_debate"],
        default="auto",
        help=(
            "Pipeline mode. 'auto' (default) picks best_r1_only / "
            "single_critique / full_debate based on roster diversity. "
            "'r1_only' runs R1 then synthesises with no debate rounds — "
            "the configuration the 2026-04 experiments found strongest "
            "for diverse rosters. Distinct from 'best_r1_only' which "
            "skips synthesis too."
        ),
    )
    parser.add_argument(
        "--synthesise",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Override whether to synthesise after the debate rounds. "
            "Default: follow the policy's built-in choice (best_r1_only "
            "skips; every other mode synthesises). Pass --no-synthesise "
            "to force skip even in a mode that would normally synthesise "
            "— useful for drafting workflows where you want to read the "
            "three R1 drafts yourself without the tool flattening them. "
            "Composes with --policy."
        ),
    )
    parser.add_argument(
        "--reports-root",
        default=str(Path.home() / ".council" / "reports"),
        help="Directory where debate reports are saved as markdown.",
    )
    parser.add_argument(
        "--summaries-root",
        default=str(Path.home() / ".council" / "summaries"),
        help=(
            "Directory where per-debate run_summary.json files are saved. "
            "Captures roster, diversity, policy, best-R1, synthesis, and "
            "preference verdict."
        ),
    )
    args = parser.parse_args()

    packs_root = Path(args.packs_root)
    packs_root.mkdir(parents=True, exist_ok=True)
    pack = (
        FilesystemPackLoader(root=packs_root).load(args.pack)
        if (packs_root / args.pack).is_dir()
        else CouncilPack(name=args.pack, shared_context=None, personas={})
    )

    config = load_config()
    cli_models: dict[ElderId, str | None] = {
        "ada": args.claude_model,
        "kai": args.gemini_model,
        "mei": args.codex_model,
    }
    elders, using_openrouter, roster_spec = build_elders(config, cli_models=cli_models)
    from council.adapters.storage.report_file import ReportFileStore

    best_r1_judge: ElderPort | None = None
    preference_judges: list[tuple[str, ElderPort]] | None = None
    if using_openrouter and config.openrouter_api_key:
        from council.adapters.elders.openrouter import OpenRouterAdapter

        # Best-R1 uses a single cheap judge (~$0.001 via gemini-flash). The
        # rubric is a straightforward "pick the strongest of three"; family
        # bias on this task is less structurally dangerous than it is on
        # preference, where the 2026-04-20 replication found judge-family
        # effects. We keep best-R1 single-judge for cost.
        best_r1_judge = OpenRouterAdapter(
            elder_id="ada",
            model="google/gemini-2.5-flash",
            api_key=config.openrouter_api_key,
        )
        # Preference is multi-judge by default — two families (Google +
        # Anthropic), both cheap. Adds ~$0.02/run. Each adapter is
        # separate so per-task cost attribution stays possible.
        preference_judges = [
            (
                "google/gemini-2.5-flash",
                OpenRouterAdapter(
                    elder_id="ada",
                    model="google/gemini-2.5-flash",
                    api_key=config.openrouter_api_key,
                ),
            ),
            (
                "anthropic/claude-haiku-4.5",
                OpenRouterAdapter(
                    elder_id="ada",
                    model="anthropic/claude-haiku-4.5",
                    api_key=config.openrouter_api_key,
                ),
            ),
        ]

    asyncio.run(
        run_headless(
            prompt=args.prompt,
            pack=pack,
            elders=elders,
            store=JsonFileStore(root=Path(args.store_root)),
            clock=SystemClock(),
            bus=InMemoryBus(),
            synthesizer=args.synthesizer,
            using_openrouter=using_openrouter,
            max_rounds=args.max_rounds,
            report_store=ReportFileStore(root=Path(args.reports_root)),
            best_r1_judge=best_r1_judge,
            preference_judges=preference_judges,
            policy=_policy_override_from_args(args.policy, args.max_rounds),
            roster_spec=roster_spec,
            run_summary_root=Path(args.summaries_root),
            synthesise_override=args.synthesise,
        )
    )

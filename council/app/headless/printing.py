from __future__ import annotations

from pathlib import Path

from council.domain.models import Debate, ElderId
from council.domain.preference import MultiJudgeVerdict, PreferenceVerdict
from council.domain.synthesis_output import SynthesisOutput

_LABELS: dict[ElderId, str] = {
    "ada": "Ada",
    "kai": "Kai",
    "mei": "Mei",
}


def label(elder: ElderId) -> str:
    return _LABELS[elder]


def print_rounds(debate: Debate) -> None:
    for rnd in debate.rounds:
        print(f"--- Round {rnd.number} ---")
        for turn in rnd.turns:
            name = _LABELS[turn.elder]
            if turn.answer.error:
                print(f"[{name}] ERROR {turn.answer.error.kind}: {turn.answer.error.detail}\n")
            else:
                print(f"[{name}] {turn.answer.text}\n")


def print_best_r1_pick(elder: ElderId, reason: str) -> None:
    print(f"\n[Best R1 (judge-picked): {_LABELS[elder]}] {reason}\n")


def print_best_r1_unavailable() -> None:
    print("\n[Best-R1 baseline unavailable (no OpenRouter judge configured).]\n")


def print_synthesis(
    *,
    structured: SynthesisOutput,
    synthesizer: ElderId,
    risk_note: str | None,
) -> None:
    print(f"\n[Synthesis by {_LABELS[synthesizer]}]\n")
    if risk_note:
        print(f"{risk_note}\n")
    print(structured.answer)
    if structured.why:
        print(f"\nWhy: {structured.why}")
    if structured.disagreements:
        print("\nDisagreements:")
        for d in structured.disagreements:
            print(f"- {d}")
    else:
        print("\nDisagreements: none material.")


def print_preference(preference: PreferenceVerdict | MultiJudgeVerdict) -> None:
    if isinstance(preference, MultiJudgeVerdict):
        print(
            f"\n[Preference judges] aggregate={preference.aggregate} "
            f"(unanimous={preference.unanimous}, "
            f"n_judges={len(preference.verdicts)})"
        )
        for jv in preference.verdicts:
            print(f"  · {jv.judge_model}: {jv.verdict.winner} — {jv.verdict.reason}")
    else:
        print(f"\n[Preference judge] {preference.winner} — {preference.reason}")


def print_report(report_md: str, *, saved_to: Path | None) -> None:
    print("\n--- Debate report ---\n")
    print(report_md)
    if saved_to is not None:
        print(f"\nReport saved to {saved_to}")


def print_best_r1_only_deliverable(debate: Debate, best_r1_text: str | None) -> None:
    if debate.best_r1_elder is not None and best_r1_text:
        print(f"[Answer (best-R1, {_LABELS[debate.best_r1_elder]})] {best_r1_text}")
    else:
        print("[warning] best-R1-only mode but no judge available — no deliverable produced.")


def print_run_summary_path(path: Path) -> None:
    print(f"\n[run summary] {path}")


def print_policy_warning(warning: str) -> None:
    print(f"[warning] {warning}")


def print_max_rounds_exhausted(max_rounds: int) -> None:
    print(
        f"[warning] Hit policy max_rounds={max_rounds} "
        "without full convergence. Synthesising best-effort."
    )


def print_report_failed(error: Exception) -> None:
    print(f"\n[warning] Report generation failed: {error}")

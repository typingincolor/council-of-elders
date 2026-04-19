from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from council.domain.models import ElderId, ElderQuestion


@dataclass(frozen=True)
class ValidationOk:
    pass


@dataclass(frozen=True)
class Violation:
    reason: str
    detail: str


ValidationResult = Union[ValidationOk, Violation]


class TurnValidator:
    """Enforces the per-phase debate contract.

    R1: silent initial — no CONVERGED, no questions.
    R2: cross-examination — no CONVERGED, exactly one question.
    R3+: open debate — CONVERGED required; if no, exactly one question.

    Returns at most one Violation per call (first failure encountered).
    `agreed=True` with questions in R3+ is NOT a violation — DebateService
    drops the questions with a warning.
    """

    def validate(
        self,
        *,
        agreed: bool | None,
        questions: tuple[ElderQuestion, ...],
        round_num: int,
        from_elder: ElderId,
    ) -> ValidationResult:
        if round_num == 1:
            if agreed is not None:
                return Violation(
                    reason="r1_unexpected_convergence",
                    detail="Round 1 is a silent initial round — do not emit CONVERGED.",
                )
            if questions:
                return Violation(
                    reason="r1_unexpected_questions",
                    detail="Round 1 is silent — do not ask questions yet.",
                )
            return ValidationOk()

        if round_num == 2:
            if agreed is not None:
                return Violation(
                    reason="r2_unexpected_convergence",
                    detail="Round 2 is cross-examination — do not emit CONVERGED yet.",
                )
            if len(questions) == 0:
                return Violation(
                    reason="r2_missing_question",
                    detail="Round 2 requires exactly one question of one peer.",
                )
            if len(questions) > 1:
                return Violation(
                    reason="r2_multiple_questions",
                    detail="Round 2 allows only one question — pick the most important one.",
                )
            return ValidationOk()

        # round_num >= 3
        if agreed is None:
            return Violation(
                reason="rn_missing_convergence",
                detail="Round 3+ requires exactly one of CONVERGED: yes or CONVERGED: no.",
            )
        if agreed is True:
            # questions dropped-with-warn by DebateService; not a violation here.
            return ValidationOk()
        # agreed is False
        if len(questions) == 0:
            return Violation(
                reason="rn_no_converged_missing_question",
                detail="If CONVERGED: no, you must ask exactly one question of a peer.",
            )
        if len(questions) > 1:
            return Violation(
                reason="rn_multiple_questions",
                detail="Round 3+ allows only one question — pick the most important one.",
            )
        return ValidationOk()

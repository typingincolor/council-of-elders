from __future__ import annotations

from typing import Protocol

from council.domain.models import Debate, ElderId, ElderQuestion, Round
from council.domain.prompting import PromptBuilder
from council.domain.validation import (
    TurnValidator,
    ValidationOk,
    ValidationResult,
    Violation,
)

__all__ = [
    "DebateRules",
    "DefaultRules",
    "ValidationOk",
    "ValidationResult",
    "Violation",
]


class DebateRules(Protocol):
    """Pluggable debate-rules policy.

    Concrete implementations define per-phase prompt content, validation
    contract, and convergence semantics. DebateService consumes the
    Protocol only; it does not know whether the ruleset is the default
    three-phase model or something else.
    """

    def system_message(self, debate: Debate, elder: ElderId) -> str: ...

    def user_message(self, debate: Debate, elder: ElderId, round_num: int) -> str: ...

    def retry_reminder(self, violation: Violation) -> str: ...

    def validate(
        self,
        *,
        agreed: bool | None,
        questions: tuple[ElderQuestion, ...],
        round_num: int,
        from_elder: ElderId,
    ) -> ValidationResult: ...

    def is_converged(self, rnd: Round) -> bool: ...


class DefaultRules:
    """Three-phase debate rules:
       R1 silent initial / R2 forced cross-exam / R3+ open with convergence.

    Thin facade over PromptBuilder and TurnValidator. Both internal helpers
    remain independently testable; DefaultRules is the seam DebateService
    depends on.
    """

    def __init__(
        self,
        *,
        prompt_builder: PromptBuilder | None = None,
        validator: TurnValidator | None = None,
    ) -> None:
        self._prompt_builder = prompt_builder or PromptBuilder()
        self._validator = validator or TurnValidator()

    def system_message(self, debate: Debate, elder: ElderId) -> str:
        return self._prompt_builder.build_system_message(debate, elder)

    def user_message(self, debate: Debate, elder: ElderId, round_num: int) -> str:
        if round_num == 1:
            return self._prompt_builder.build_round_1_user(debate)
        if round_num == 2:
            return self._prompt_builder.build_round_2_user(debate, elder)
        return self._prompt_builder.build_round_n_user(debate, elder, round_num)

    def retry_reminder(self, violation: Violation) -> str:
        return self._prompt_builder.build_retry_reminder(violation.detail)

    def validate(
        self,
        *,
        agreed: bool | None,
        questions: tuple[ElderQuestion, ...],
        round_num: int,
        from_elder: ElderId,
    ) -> ValidationResult:
        return self._validator.validate(
            agreed=agreed,
            questions=questions,
            round_num=round_num,
            from_elder=from_elder,
        )

    def is_converged(self, rnd: Round) -> bool:
        return rnd.converged()

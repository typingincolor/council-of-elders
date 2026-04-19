from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from council.domain.models import ElderAnswer, ElderError, ElderId, ElderQuestion, Round, UserMessage


@dataclass(frozen=True)
class TurnStarted:
    elder: ElderId
    round_number: int


@dataclass(frozen=True)
class TurnCompleted:
    elder: ElderId
    round_number: int
    answer: ElderAnswer
    questions: tuple[ElderQuestion, ...] = ()


@dataclass(frozen=True)
class TurnFailed:
    elder: ElderId
    round_number: int
    error: ElderError


@dataclass(frozen=True)
class RoundCompleted:
    round: Round


@dataclass(frozen=True)
class SynthesisCompleted:
    answer: ElderAnswer


@dataclass(frozen=True)
class DebateAbandoned:
    pass


@dataclass(frozen=True)
class UserMessageReceived:
    message: UserMessage


DebateEvent = Union[
    TurnStarted,
    TurnCompleted,
    TurnFailed,
    RoundCompleted,
    SynthesisCompleted,
    DebateAbandoned,
    UserMessageReceived,
]

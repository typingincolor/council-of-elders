from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, NamedTuple

ElderId = Literal["claude", "gemini", "chatgpt"]

Role = Literal["system", "user", "assistant"]


class Message(NamedTuple):
    role: Role
    content: str


ErrorKind = Literal[
    "timeout",
    "cli_missing",
    "auth_failed",
    "quota_exhausted",
    "nonzero_exit",
    "unparseable",
]
DebateStatus = Literal["in_progress", "synthesized", "abandoned"]


@dataclass(frozen=True)
class ElderError:
    elder: ElderId
    kind: ErrorKind
    detail: str


@dataclass(frozen=True)
class ElderAnswer:
    elder: ElderId
    text: str | None
    error: ElderError | None
    agreed: bool | None
    created_at: datetime


@dataclass(frozen=True)
class UserMessage:
    text: str
    after_round: int
    created_at: datetime


@dataclass(frozen=True)
class ElderQuestion:
    from_elder: ElderId
    to_elder: ElderId
    text: str
    round_number: int


@dataclass(frozen=True)
class Turn:
    elder: ElderId
    answer: ElderAnswer
    questions: tuple[ElderQuestion, ...] = ()


@dataclass
class Round:
    number: int
    turns: list[Turn]

    def converged(self) -> bool:
        if len(self.turns) != 3:
            return False
        if len({t.elder for t in self.turns}) != 3:
            return False
        return all(t.answer.agreed is True for t in self.turns)


@dataclass
class CouncilPack:
    name: str
    shared_context: str | None
    personas: dict[ElderId, str]


@dataclass
class Debate:
    id: str
    prompt: str
    pack: CouncilPack
    rounds: list[Round]
    status: DebateStatus
    synthesis: ElderAnswer | None
    user_messages: list[UserMessage] = field(default_factory=list)
    best_r1_elder: ElderId | None = None

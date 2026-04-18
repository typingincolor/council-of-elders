from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ElderId = Literal["claude", "gemini", "chatgpt"]
ErrorKind = Literal[
    "timeout",
    "cli_missing",
    "auth_failed",
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
class Turn:
    elder: ElderId
    answer: ElderAnswer


@dataclass
class Round:
    number: int
    turns: list[Turn]

    def converged(self) -> bool:
        if len(self.turns) != 3:
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

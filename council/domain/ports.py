from __future__ import annotations

from datetime import datetime
from typing import AsyncIterator, Protocol

from council.domain.events import DebateEvent
from council.domain.models import CouncilPack, Debate, ElderId


class ElderPort(Protocol):
    elder_id: ElderId

    async def ask(self, prompt: str, *, timeout_s: float = 45.0) -> str: ...

    async def health_check(self) -> bool: ...


class TranscriptStore(Protocol):
    def save(self, debate: Debate) -> None: ...

    def load(self, debate_id: str) -> Debate: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class CouncilPackLoader(Protocol):
    def load(self, pack_name_or_path: str) -> CouncilPack: ...


class EventBus(Protocol):
    async def publish(self, event: DebateEvent) -> None: ...

    def subscribe(self) -> AsyncIterator[DebateEvent]: ...

from __future__ import annotations

from datetime import datetime
from typing import AsyncIterator, Protocol

from council.domain.events import DebateEvent
from council.domain.models import CouncilPack, Debate, ElderId, Message


class ElderPort(Protocol):
    elder_id: ElderId

    async def ask(self, conversation: list[Message], *, timeout_s: float = 45.0) -> str: ...

    async def health_check(self) -> bool: ...


class TranscriptStore(Protocol):
    def save(self, debate: Debate) -> None: ...

    def load(self, debate_id: str) -> Debate: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class CouncilPackLoader(Protocol):
    def load(self, pack_name_or_path: str) -> CouncilPack: ...


class EventBus(Protocol):
    """Pub/sub bus for DebateEvents.

    Implementation contract for `subscribe`:

        async def subscribe(self) -> AsyncIterator[DebateEvent]:
            while True:
                yield await self._queue.get()

    That is, `subscribe` is expected to be an async generator function — a
    plain `async def` with `yield` inside. Calling it returns an
    AsyncGenerator (a subtype of AsyncIterator) without needing `await`, so
    callers iterate with `async for ev in bus.subscribe(): ...`.

    The Protocol signature below uses `def` rather than `async def` because
    at the call site an async generator function is invoked like a plain
    function — the returned AsyncIterator is produced synchronously and
    iteration happens via `async for`.
    """

    async def publish(self, event: DebateEvent) -> None: ...

    def subscribe(self) -> AsyncIterator[DebateEvent]: ...

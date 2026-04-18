from __future__ import annotations

import asyncio
from typing import AsyncIterator

from council.domain.events import DebateEvent


class InMemoryBus:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[DebateEvent] = asyncio.Queue()

    async def publish(self, event: DebateEvent) -> None:
        await self._queue.put(event)

    async def subscribe(self) -> AsyncIterator[DebateEvent]:
        while True:
            ev = await self._queue.get()
            yield ev

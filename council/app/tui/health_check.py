from __future__ import annotations

import asyncio

from council.app.tui.notices import CouncilNotices
from council.domain.models import ElderId
from council.domain.ports import ElderPort


class HealthChecker:
    """Probe elder CLIs and surface unavailability notices."""

    def __init__(
        self,
        *,
        elders: dict[ElderId, ElderPort],
        labels: dict[ElderId, str],
    ) -> None:
        self._elders = elders
        self._labels = labels

    async def run(self, notices: CouncilNotices) -> bool:
        """Run all probes. Returns True iff every elder is unhealthy
        (caller should disable input because nothing can answer).
        """
        results = await asyncio.gather(*(self._probe(eid) for eid in self._elders))
        unhealthy = [eid for eid, ok in results if not ok]
        if not unhealthy:
            return False
        for eid in unhealthy:
            notices.write(
                f"[yellow]⚠ {self._labels[eid]} CLI is unavailable or unauthenticated. "
                f"Install it and run its `login` command before asking a question.[/yellow]"
            )
        if len(unhealthy) == len(self._elders):
            notices.write(
                "[red]No elders available. Fix the vendor CLI setup above, "
                "then restart the app.[/red]"
            )
            return True
        return False

    async def _probe(self, elder_id: ElderId) -> tuple[ElderId, bool]:
        try:
            ok = await self._elders[elder_id].health_check()
        except Exception:
            ok = False
        return elder_id, ok

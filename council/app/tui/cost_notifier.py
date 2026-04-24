from __future__ import annotations

from council.app.tui.notices import CouncilNotices
from council.domain.models import ElderId
from council.domain.ports import ElderPort


class CostNotifier:
    """Emits OpenRouter cost deltas as blue notices, round-by-round.

    Only meaningful when at least one elder is an ``OpenRouterAdapter``;
    for subprocess-only rosters the emit is a no-op (delta is 0 and the
    formatted notice reflects that).
    """

    def __init__(self, elders: dict[ElderId, ElderPort]) -> None:
        self._elders = elders
        self._prev_total: float = 0.0

    async def emit(self, notices: CouncilNotices) -> None:
        from council.adapters.elders.openrouter import (
            OpenRouterAdapter,
            format_cost_notice,
        )

        current = sum(
            e.session_cost_usd for e in self._elders.values() if isinstance(e, OpenRouterAdapter)
        )
        delta = current - self._prev_total
        self._prev_total = current

        any_or = next(
            (e for e in self._elders.values() if isinstance(e, OpenRouterAdapter)),
            None,
        )
        used, limit = (0.0, None)
        if any_or is not None:
            used, limit = await any_or.fetch_credits()

        line = format_cost_notice(
            elders=self._elders,
            round_cost_delta_usd=delta,
            credits_used=used,
            credits_limit=limit,
        )
        notices.write(f"[blue]{line}[/blue]")

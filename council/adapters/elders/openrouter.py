from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from council.domain.models import ElderId, ErrorKind


class OpenRouterError(Exception):
    def __init__(self, kind: ErrorKind, detail: str) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind: ErrorKind = kind
        self.detail: str = detail


@dataclass
class OpenRouterAdapter:
    elder_id: ElderId
    model: str
    api_key: str
    client: httpx.AsyncClient | None = None
    session_cost_usd: float = 0.0
    session_tokens: dict[str, int] = field(
        default_factory=lambda: {"prompt": 0, "completion": 0}
    )

    async def ask(self, prompt: str, *, timeout_s: float = 45.0) -> str:
        raise NotImplementedError

    async def health_check(self) -> bool:
        return bool(self.api_key)

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from council.domain.models import ElderId, ErrorKind


class OpenRouterError(Exception):
    def __init__(self, kind: ErrorKind, detail: str) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind: ErrorKind = kind
        self.detail: str = detail


_BASE_URL = "https://openrouter.ai"
_CHAT_PATH = "/api/v1/chat/completions"
_REFERER = "https://github.com/typingincolor/council-of-elders"
_TITLE = "council-of-elders"


async def _post_chat(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    prompt: str,
    timeout_s: float,
) -> httpx.Response:
    return await client.post(
        _CHAT_PATH,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": _REFERER,
            "X-Title": _TITLE,
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "usage": {"include": True},
        },
        timeout=timeout_s,
    )


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
        client = self.client or httpx.AsyncClient(base_url=_BASE_URL)
        owned = self.client is None
        try:
            try:
                resp = await _post_chat(
                    client, self.api_key, self.model, prompt, timeout_s
                )
            except httpx.TimeoutException as ex:
                raise OpenRouterError("timeout", str(ex)) from ex
            except httpx.HTTPError as ex:
                raise OpenRouterError("nonzero_exit", f"network error: {ex}") from ex

            if resp.status_code in (401, 403):
                raise OpenRouterError("auth_failed", resp.text[-400:])
            if resp.status_code == 429:
                raise OpenRouterError("quota_exhausted", resp.text[-400:])
            if resp.status_code >= 400:
                raise OpenRouterError(
                    "nonzero_exit", f"HTTP {resp.status_code}: {resp.text[-400:]}"
                )

            try:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError) as ex:
                raise OpenRouterError(
                    "unparseable", f"unexpected response shape: {ex}"
                ) from ex
        finally:
            if owned:
                await client.aclose()

    async def health_check(self) -> bool:
        return bool(self.api_key)

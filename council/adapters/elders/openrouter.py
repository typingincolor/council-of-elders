from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from council.domain.models import ElderId, ErrorKind, Message


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
    conversation: list[Message],
    timeout_s: float,
) -> httpx.Response:
    messages = [{"role": role, "content": content} for role, content in conversation]
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
            "messages": messages,
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
    session_tokens: dict[str, int] = field(default_factory=lambda: {"prompt": 0, "completion": 0})

    async def ask(self, conversation: list[Message], *, timeout_s: float = 45.0) -> str:
        if not conversation:
            raise ValueError("conversation must be non-empty")
        client = self.client or httpx.AsyncClient(base_url=_BASE_URL)
        owned = self.client is None
        try:
            try:
                resp = await _post_chat(client, self.api_key, self.model, conversation, timeout_s)
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
                message = data["choices"][0]["message"]
            except (ValueError, KeyError, IndexError, TypeError) as ex:
                raise OpenRouterError("unparseable", f"unexpected response shape: {ex}") from ex

            # Thinking models (e.g. gemini-2.5-pro) sometimes emit all output
            # into `reasoning` and leave `content` empty. Fall back so the
            # elder is never silent; only raise if both are empty.
            content = (message.get("content") or "").strip()
            if not content:
                reasoning = (message.get("reasoning") or "").strip()
                if reasoning:
                    content = reasoning
                else:
                    raise OpenRouterError(
                        "unparseable",
                        f"model returned empty content and no reasoning (model={self.model})",
                    )

            usage = data.get("usage") or {}
            cost = usage.get("cost")
            if isinstance(cost, (int, float)):
                self.session_cost_usd += float(cost)
            self.session_tokens["prompt"] += int(usage.get("prompt_tokens") or 0)
            self.session_tokens["completion"] += int(usage.get("completion_tokens") or 0)
            return content
        finally:
            if owned:
                await client.aclose()

    async def fetch_credits(self) -> tuple[float, float | None]:
        client = self.client or httpx.AsyncClient(base_url=_BASE_URL)
        owned = self.client is None
        try:
            try:
                resp = await client.get(
                    "/api/v1/credits",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10.0,
                )
                data = resp.json().get("data", {}) if resp.status_code == 200 else {}
            except (httpx.HTTPError, ValueError):
                return (0.0, None)
            used = float(data.get("total_usage") or 0.0)
            limit_raw = data.get("total_credits")
            limit = float(limit_raw) if isinstance(limit_raw, (int, float)) else None
            return (used, limit)
        finally:
            if owned:
                await client.aclose()

    async def health_check(self) -> bool:
        return bool(self.api_key)


def format_cost_notice(
    elders: dict,  # dict[ElderId, ElderPort]
    round_cost_delta_usd: float,
    credits_used: float,
    credits_limit: float | None,
) -> str:
    session_total = sum(getattr(e, "session_cost_usd", 0.0) for e in elders.values())
    parts = [
        "[openrouter]",
        f"round: ${round_cost_delta_usd:.4f}",
        f"session: ${session_total:.4f}",
    ]
    if credits_limit is not None:
        remaining = max(credits_limit - credits_used, 0.0)
        parts.append(f"credits remaining: ${remaining:.2f}")
    else:
        parts.append(f"credits used: ${credits_used:.2f}")
    return " · ".join(parts)

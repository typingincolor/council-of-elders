from __future__ import annotations

from council.domain.models import Message

_TAG = {"system": "SYSTEM", "user": "USER", "assistant": "ASSISTANT"}


def flatten_conversation(conv: list[Message]) -> str:
    if not conv:
        raise ValueError("conversation must be non-empty")
    parts = [f"{_TAG[role]}:\n{content}" for role, content in conv]
    return "\n\n".join(parts)

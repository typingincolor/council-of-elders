"""Slot-id migration for the vendor-name → generic-name rename.

When elder slots were renamed from claude/gemini/chatgpt → alpha/beta/gamma
we kept a translation table so persisted artifacts (saved debate JSONs,
OpenRouter config TOML keys) continue to load without user intervention.

This module is the single source of truth for the mapping. Readers
(``JsonFileStore.load``, ``load_config``) consult it; everything else
uses the current ``ElderId`` literal directly.
"""

from __future__ import annotations

from council.domain.models import ElderId

LEGACY_TO_CURRENT: dict[str, ElderId] = {
    "claude": "ada",
    "gemini": "kai",
    "chatgpt": "mei",
}


def migrate_slot_id(slot: str) -> ElderId:
    """Return the current slot id for an incoming value.

    If ``slot`` is already a current id, returns it unchanged. If it's a
    legacy vendor name, returns the mapped current id. Anything else
    raises — we never silently tolerate unknown slots, because that
    would hide data corruption.
    """
    if slot in ("ada", "kai", "mei"):
        return slot  # type: ignore[return-value]
    if slot in LEGACY_TO_CURRENT:
        return LEGACY_TO_CURRENT[slot]
    raise ValueError(f"Unknown elder slot id: {slot!r}")

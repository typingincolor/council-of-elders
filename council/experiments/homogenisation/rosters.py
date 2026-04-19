"""Roster definitions and elder-adapter construction for the
homogenisation probe.

The three rosters isolate two mechanisms the council tool could
deliver value through: model diversity (mixed vs homogeneous) and
debate protocol (homogeneous vs single-model baseline). The
substituted roster is the original issue 11 question — does a
distant-lineage model widen diversity further?
"""

from __future__ import annotations

from dataclasses import dataclass

from council.adapters.elders.openrouter import OpenRouterAdapter
from council.domain.models import ElderId
from council.domain.ports import ElderPort


@dataclass(frozen=True)
class RosterSpec:
    name: str
    models: dict[ElderId, str]


ROSTERS: tuple[RosterSpec, ...] = (
    RosterSpec(
        name="homogeneous",
        models={
            "claude": "openai/gpt-5-mini",
            "gemini": "openai/gpt-5-mini",
            "chatgpt": "openai/gpt-5-mini",
        },
    ),
    RosterSpec(
        name="mixed_baseline",
        models={
            "claude": "anthropic/claude-sonnet-4.5",
            "gemini": "google/gemini-2.5-pro",
            "chatgpt": "openai/gpt-5",
        },
    ),
    RosterSpec(
        name="substituted",
        models={
            "claude": "anthropic/claude-sonnet-4.5",
            "gemini": "meta-llama/llama-3.1-70b-instruct",
            "chatgpt": "openai/gpt-5",
        },
    ),
)


def build_roster_elders(spec: RosterSpec, *, api_key: str) -> dict[ElderId, ElderPort]:
    """Build a fresh {slot → OpenRouterAdapter} mapping for a roster.

    Adapters own their HTTP client implicitly via OpenRouterAdapter's
    per-call client creation, so each roster's adapters can be discarded
    at the end of its run without explicit cleanup.
    """
    return {
        slot: OpenRouterAdapter(elder_id=slot, model=model, api_key=api_key)
        for slot, model in spec.models.items()
    }

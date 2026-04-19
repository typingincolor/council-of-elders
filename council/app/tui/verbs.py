"""Thinking-state verbs for the TUI.

When an elder (or the synthesiser) is mid-turn, its pane label cycles through
a rotating whimsical verb plus an elapsed-seconds counter. Elder-themed
vocabulary fits the "council of elders" metaphor.
"""
from __future__ import annotations

import random
from typing import Protocol

VERB_POOL: tuple[str, ...] = (
    "Pondering",
    "Deliberating",
    "Ruminating",
    "Mulling",
    "Reflecting",
    "Brewing",
    "Cogitating",
    "Meditating",
    "Musing",
    "Noodling",
    "Pontificating",
    "Contemplating",
)


class VerbChooser(Protocol):
    """Callable that returns a thinking verb to display."""

    def __call__(self) -> str: ...


class RandomVerbChooser:
    """Default chooser — picks uniformly from VERB_POOL per call."""

    def __call__(self) -> str:
        return random.choice(VERB_POOL)


class FixedVerbChooser:
    """Deterministic chooser for tests."""

    def __init__(self, verb: str) -> None:
        self._verb = verb

    def __call__(self) -> str:
        return self._verb

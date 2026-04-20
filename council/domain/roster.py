"""Domain-level roster specification.

Represents the (slot → model-id) mapping for a council. Promoted from
``council/experiments/homogenisation/rosters.py`` so the main app and
experiments share the same type under the diversity-engine direction
(``docs/superpowers/plans/2026-04-20-diversity-engine-refactor.md``).
"""
from __future__ import annotations

from dataclasses import dataclass

from council.domain.models import ElderId


@dataclass(frozen=True)
class RosterSpec:
    name: str
    models: dict[ElderId, str]

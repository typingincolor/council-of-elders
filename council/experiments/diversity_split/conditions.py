"""The 2×2 model × role matrix.

Isolates whether value comes from model diversity, role (persona)
diversity, or both. Under the diversity-engine direction the working
hypothesis is that model diversity is the primary driver; this
experiment is the calibration test — if B (same model × different
roles) performs like C (different models × same role), role diversity
is a substitute for model diversity and the positioning needs to
change. If B stays close to A and only C + D improve, personas are
not substitutes.

See ``docs/superpowers/plans/2026-04-20-diversity-engine-refactor.md``.
"""
from __future__ import annotations

from dataclasses import dataclass

from council.domain.models import CouncilPack
from council.domain.roster import RosterSpec


@dataclass(frozen=True)
class Condition:
    name: str  # e.g. "same_model_same_role"
    roster: RosterSpec
    pack: CouncilPack
    description: str


# --- rosters --------------------------------------------------------

_SAME_MODEL = RosterSpec(
    name="same_model",
    models={
        "claude": "openai/gpt-5-mini",
        "gemini": "openai/gpt-5-mini",
        "chatgpt": "openai/gpt-5-mini",
    },
)

# Matches the "substituted" roster from the homogenisation probe — the
# arm that performed best (synthesis-beats-best-R1 preference = 0.625).
_DIFF_MODEL = RosterSpec(
    name="diff_model",
    models={
        "claude": "anthropic/claude-sonnet-4.5",
        "gemini": "meta-llama/llama-3.1-70b-instruct",
        "chatgpt": "openai/gpt-5",
    },
)


# --- packs ----------------------------------------------------------
# Personas are intentionally neutral / reasoning-style based, not
# model-specific. They cover three distinct cognitive axes:
#   - skeptic: surfaces hidden assumptions, demands evidence
#   - implementer: focuses on concrete steps, constraints, who/when
#   - strategist: looks across trade-offs for leverage
#
# Slot-to-persona mapping is fixed so results are comparable across
# debates. The labels "Claude/Gemini/ChatGPT" in prompts are orthogonal
# to these personas — elders still see peer names as those handles.
# Revise these strings after the first run if they show bias or model-
# family affinity; they are provisional and open to iteration.

_BARE_PACK = CouncilPack(name="bare", shared_context=None, personas={})

_ROLES_PACK = CouncilPack(
    name="roles",
    shared_context=None,
    personas={
        "claude": (
            "You are the skeptic of the council. Your job is to surface "
            "hidden assumptions and demand evidence. Challenge load-bearing "
            "claims; ask what would have to be true for the proposal to "
            "fail. Do not play devil's advocate for its own sake — only "
            "raise objections that would change a careful decision-maker's "
            "action."
        ),
        "gemini": (
            "You are the implementer of the council. Your job is to focus "
            "on concrete steps, constraints, who does what, and by when. "
            "Translate abstract recommendations into specific first moves "
            "and name what blocks them. Avoid high-altitude framing when "
            "a concrete plan is what's needed."
        ),
        "chatgpt": (
            "You are the strategist of the council. Your job is to look "
            "across the trade-offs and find the highest-leverage move. "
            "Pay attention to second-order effects and what the decision "
            "forecloses or enables. Avoid indecisive both-sides framing — "
            "commit to a ranking of options."
        ),
    },
)


# --- 2×2 conditions -------------------------------------------------

CONDITIONS: tuple[Condition, ...] = (
    Condition(
        name="same_model_same_role",
        roster=_SAME_MODEL,
        pack=_BARE_PACK,
        description="Cell A — no diversity control. Matches the existing homogeneous arm.",
    ),
    Condition(
        name="same_model_diff_role",
        roster=_SAME_MODEL,
        pack=_ROLES_PACK,
        description="Cell B — role diversity only; tests whether personas substitute for model diversity.",
    ),
    Condition(
        name="diff_model_same_role",
        roster=_DIFF_MODEL,
        pack=_BARE_PACK,
        description="Cell C — model diversity only. Matches the existing substituted arm.",
    ),
    Condition(
        name="diff_model_diff_role",
        roster=_DIFF_MODEL,
        pack=_ROLES_PACK,
        description="Cell D — both axes. Tests whether the two diversity sources compose.",
    ),
)

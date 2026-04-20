"""Preference judge — synthesis vs best-R1.

Asks a judge which of two answers better addresses the user's question.
X/Y slots are randomised per call to defuse positional bias; the
returned ``winner`` resolves back to ``"synthesis" | "best_r1" | "tie"``.

Used by the observability layer to populate ``run_summary.json`` with
the signal the diversity-engine refocus exists to validate:

  "synthesis beats best-R1 more often in high-diversity than in
   low-diversity runs."

See ``docs/superpowers/plans/2026-04-20-diversity-engine-refactor.md``.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Literal

from council.domain.models import Message
from council.domain.ports import ElderPort

PreferenceWinner = Literal["synthesis", "best_r1", "tie"]


@dataclass(frozen=True)
class PreferenceVerdict:
    winner: PreferenceWinner
    reason: str
    raw: str


PREFERENCE_PROMPT = """You are judging which of two answers better addresses the question.

User's question:
<<<
{question}
>>>

Answer X:
<<<
{answer_x}
>>>

Answer Y:
<<<
{answer_y}
>>>

Judge on: factual correctness, completeness, shape-fit (does the form match what was asked for — e.g., headline vs essay), and avoidance of bloat. DO NOT favour an answer just because it is longer or more formal — penalise bloat.

Emit EXACTLY:
winner: X | Y | TIE
reason: one sentence."""

_WINNER_RE = re.compile(r"^\s*winner\s*:\s*(X|Y|TIE)\b", re.MULTILINE | re.IGNORECASE)
_REASON_RE = re.compile(r"^\s*reason\s*:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)
_FENCE_RE = re.compile(r"^```[a-z]*\n?|\n?```$", re.MULTILINE)


def _resolve_winner(letter: str, x_was: str) -> PreferenceWinner:
    other: PreferenceWinner = "best_r1" if x_was == "synthesis" else "synthesis"
    if letter.upper() == "TIE":
        return "tie"
    if letter.upper() == "X":
        return x_was  # type: ignore[return-value]
    return other


async def judge_preference(
    *,
    question: str,
    synthesis: str,
    best_r1: str,
    judge_port: ElderPort,
    rng: random.Random | None = None,
) -> PreferenceVerdict:
    rng = rng or random.Random()
    # Randomise which answer occupies the X slot to defuse positional bias.
    if rng.random() < 0.5:
        answer_x, answer_y, x_was = synthesis, best_r1, "synthesis"
    else:
        answer_x, answer_y, x_was = best_r1, synthesis, "best_r1"

    prompt = PREFERENCE_PROMPT.format(
        question=question.strip(),
        answer_x=answer_x.strip(),
        answer_y=answer_y.strip(),
    )
    raw = await judge_port.ask([Message("user", prompt)])
    cleaned = _FENCE_RE.sub("", raw.strip())
    winner_m = _WINNER_RE.search(cleaned)
    reason_m = _REASON_RE.search(cleaned)
    if winner_m is None:
        return PreferenceVerdict(winner="tie", reason="", raw=raw)
    return PreferenceVerdict(
        winner=_resolve_winner(winner_m.group(1), x_was),
        reason=reason_m.group(1).strip() if reason_m else "",
        raw=raw,
    )

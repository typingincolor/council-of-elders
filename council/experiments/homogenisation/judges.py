"""Judge rubrics and parsers for the homogenisation probe.

Three judges, all using the same cheap judge model via OpenRouter:

- Claim-overlap (pairwise): compares two R1 answers, emits shared /
  a-only / b-only claim counts. Called 3 times per prompt per roster.
- Best-R1 picker: sees the three R1 answers, picks the strongest.
  Called 1 time per debate.
- Preference: compares best-R1 and synthesis, picks the better answer.
  Called 1 time per debate with X/Y randomisation.

All three follow the same pattern as `_parse_drift_verdict` in
`council/domain/debate_analytics.py`: regex-based tolerant parsing,
neutral defaults on missing fields, raw response retained for
diagnostics.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass


# ---- Claim-overlap judge --------------------------------------------


@dataclass(frozen=True)
class JaccardObservation:
    shared: int
    a_only: int
    b_only: int
    note: str
    raw: str

    @property
    def jaccard(self) -> float:
        total = self.shared + self.a_only + self.b_only
        return self.shared / total if total else 0.0


CLAIM_OVERLAP_PROMPT = """You are a neutral judge comparing two answers to the same question, measuring CLAIM OVERLAP.

User's question:
<<<
{question}
>>>

Answer A:
<<<
{answer_a}
>>>

Answer B:
<<<
{answer_b}
>>>

For each distinct factual or evaluative claim either answer makes, classify it as:
- SHARED: both make this claim (possibly in different words)
- A_ONLY: only A makes it
- B_ONLY: only B makes it

"Claim" = an atomic assertion about the world, a recommendation, or a judgement (not a stylistic choice or framing decision). Two answers saying "X is faster" and "X outperforms on speed" are the same claim.

Emit EXACTLY these four lines, nothing else:
shared_count: N
a_only_count: N
b_only_count: N
note: one short sentence explaining any judgement calls."""


_SHARED_RE = re.compile(r"^\s*shared_count\s*:\s*(\d+)", re.MULTILINE | re.IGNORECASE)
_A_ONLY_RE = re.compile(r"^\s*a_only_count\s*:\s*(\d+)", re.MULTILINE | re.IGNORECASE)
_B_ONLY_RE = re.compile(r"^\s*b_only_count\s*:\s*(\d+)", re.MULTILINE | re.IGNORECASE)
_NOTE_RE = re.compile(r"^\s*note\s*:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)


def _strip_markdown_fence(raw: str) -> str:
    return re.sub(r"^```[a-z]*\n?|\n?```$", "", raw.strip(), flags=re.MULTILINE)


def _parse_claim_overlap(raw: str) -> JaccardObservation:
    cleaned = _strip_markdown_fence(raw)
    shared_m = _SHARED_RE.search(cleaned)
    a_only_m = _A_ONLY_RE.search(cleaned)
    b_only_m = _B_ONLY_RE.search(cleaned)
    note_m = _NOTE_RE.search(cleaned)
    return JaccardObservation(
        shared=int(shared_m.group(1)) if shared_m else 0,
        a_only=int(a_only_m.group(1)) if a_only_m else 0,
        b_only=int(b_only_m.group(1)) if b_only_m else 0,
        note=note_m.group(1).strip() if note_m else "",
        raw=raw,
    )


# ---- Best-R1 picker judge -------------------------------------------


@dataclass(frozen=True)
class BestR1Observation:
    best_index: int  # 1, 2, or 3
    reason: str
    raw: str


BEST_R1_PROMPT = """You will see three candidate answers to the user's question. Pick the single strongest one on correctness, completeness, and shape-fit. Ignore stylistic polish. Do not favour longer answers.

User's question:
<<<
{question}
>>>

Answer 1:
<<<
{answer_1}
>>>

Answer 2:
<<<
{answer_2}
>>>

Answer 3:
<<<
{answer_3}
>>>

Emit EXACTLY:
best: 1 | 2 | 3
reason: one sentence."""


_BEST_RE = re.compile(r"^\s*best\s*:\s*([1-3])\b", re.MULTILINE | re.IGNORECASE)
_REASON_RE = re.compile(r"^\s*reason\s*:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)


def _parse_best_r1(raw: str) -> BestR1Observation:
    cleaned = _strip_markdown_fence(raw)
    best_m = _BEST_RE.search(cleaned)
    reason_m = _REASON_RE.search(cleaned)
    return BestR1Observation(
        best_index=int(best_m.group(1)) if best_m else 1,
        reason=reason_m.group(1).strip() if reason_m else "",
        raw=raw,
    )


# ---- Preference judge -----------------------------------------------


@dataclass(frozen=True)
class PreferenceObservation:
    winner: str  # "synthesis" | "best_r1" | "tie"
    reason: str
    raw: str
    x_was: str  # "synthesis" or "best_r1"


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


def _shuffle_xy(
    synthesis: str, best_r1: str, rng: random.Random
) -> tuple[str, str, str]:
    """Randomly decide whether synthesis goes to the X or Y slot.

    Returns (answer_x_text, answer_y_text, x_was) where `x_was` is
    "synthesis" or "best_r1". Use a seeded `random.Random` for
    reproducibility.
    """
    if rng.random() < 0.5:
        return synthesis, best_r1, "synthesis"
    return best_r1, synthesis, "best_r1"


def _resolve_preference_winner(x_or_y: str, x_was: str) -> str:
    if x_or_y.upper() == "TIE":
        return "tie"
    other = "best_r1" if x_was == "synthesis" else "synthesis"
    if x_or_y.upper() == "X":
        return x_was
    return other


def _parse_preference(raw: str, *, x_was: str) -> PreferenceObservation:
    cleaned = _strip_markdown_fence(raw)
    winner_m = _WINNER_RE.search(cleaned)
    reason_m = _REASON_RE.search(cleaned)
    if winner_m is None:
        return PreferenceObservation(winner="tie", reason="", raw=raw, x_was=x_was)
    winner = _resolve_preference_winner(winner_m.group(1), x_was)
    return PreferenceObservation(
        winner=winner,
        reason=reason_m.group(1).strip() if reason_m else "",
        raw=raw,
        x_was=x_was,
    )

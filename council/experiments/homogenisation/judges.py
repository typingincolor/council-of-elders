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

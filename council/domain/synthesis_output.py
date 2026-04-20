"""Structured synthesis output — Answer / Why / Disagreements.

Under the diversity-engine direction, the synthesised deliverable is no
longer a single prose block: it carries the answer, a short rationale,
and decision-relevant disagreements the council surfaced. The
synthesiser is prompted to emit three labelled sections. Parsing is
tolerant — missing sections default to empty strings / empty tuples;
if no recognised label is present, the whole raw text is treated as the
answer so a rule-ignoring model still yields a usable deliverable.

See ``docs/superpowers/plans/2026-04-20-diversity-engine-refactor.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_ANSWER_RE = re.compile(
    r"^\s*ANSWER\s*:\s*\n(.*?)(?=\n\s*(?:WHY|DISAGREEMENTS)\s*:\s*\n|\Z)",
    re.DOTALL | re.MULTILINE | re.IGNORECASE,
)
_WHY_RE = re.compile(
    r"^\s*WHY\s*:\s*\n(.*?)(?=\n\s*(?:ANSWER|DISAGREEMENTS)\s*:\s*\n|\Z)",
    re.DOTALL | re.MULTILINE | re.IGNORECASE,
)
_DISAGREEMENTS_RE = re.compile(
    r"^\s*DISAGREEMENTS\s*:\s*\n(.*?)(?=\n\s*(?:ANSWER|WHY)\s*:\s*\n|\Z)",
    re.DOTALL | re.MULTILINE | re.IGNORECASE,
)


@dataclass(frozen=True)
class SynthesisOutput:
    answer: str
    why: str
    disagreements: tuple[str, ...]
    raw: str


def parse_synthesis(raw: str) -> SynthesisOutput:
    body = raw.strip()
    answer_m = _ANSWER_RE.search(body)
    why_m = _WHY_RE.search(body)
    disag_m = _DISAGREEMENTS_RE.search(body)

    # No recognised labels at all → best-effort: treat whole body as the answer.
    if answer_m is None and why_m is None and disag_m is None:
        return SynthesisOutput(answer=body, why="", disagreements=(), raw=raw)

    answer = answer_m.group(1).strip() if answer_m else ""
    why = why_m.group(1).strip() if why_m else ""
    disagreements: tuple[str, ...] = ()
    if disag_m:
        block = disag_m.group(1).strip()
        if block and block.lower() != "(none)":
            items: list[str] = []
            for line in block.splitlines():
                s = line.strip()
                if not s or s.lower() == "(none)":
                    continue
                s = re.sub(r"^[-*]\s*", "", s)
                if s:
                    items.append(s)
            disagreements = tuple(items)
    return SynthesisOutput(answer=answer, why=why, disagreements=disagreements, raw=raw)

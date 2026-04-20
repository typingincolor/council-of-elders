"""Post-generation structural validator for synthesiser output.

Detects known failure modes in synthesis text that the prompt alone cannot
fully eliminate — particularly chain-of-thought leakage on fast-tier models
where "silently check your output" instructions don't hold and draft-style
headings leak into the response.

Motivation and detection signals come from the council meta-debate
`5142e6fc` (recorded under `~/.council/reports/5142e6fc-...md`). The key
insight from that debate: prompt-only mitigation is necessary but
insufficient for decoding-pathology classes of failure. A cheap
post-generation regex gate plus a single regenerate on failure gives
belt-and-braces reliability for the user-facing artifact.

This module is pure: no I/O, no LLM calls. It consumes text and returns
a ValidationResult.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class SynthesisOk:
    pass


@dataclass(frozen=True)
class SynthesisViolation:
    reason: str
    detail: str


SynthesisResult = Union[SynthesisOk, SynthesisViolation]


# Detection patterns
# ----------------------------------------------------------------------

# Repeated bolded headers — the Gemini-flash CoT-loop signature.
# Looks like `**Defining Goals**` or `**Refining the Core Objective**`.
_BOLD_HEADER_RE = re.compile(r"\*\*[A-Z][A-Za-z0-9 ,\-]+\*\*")

# Preamble at the start of the synthesis — the first-token-anchor failure.
# Case-insensitive match against the first ~60 characters.
_PREAMBLE_RE = re.compile(
    r"^\s*(okay|sure|alright|so[,\s]|"
    r"here(\s+(is|are))?(\s*[,:'])?(\s*'s)?|"
    r"here's\b|"
    r"let\s+me|my\s+(final\s+)?answer|the\s+answer\s+is|"
    r"to\s+answer\s+your\s+question)",
    re.IGNORECASE,
)

# Draft-label strings the prompt bans explicitly. These are not ALL
# occurrences (markdown is fine); they match a draft-label emission
# pattern where the label is at the start of a line.
_DRAFT_LABEL_RES = [
    re.compile(r"^\s*\*?\*?(Defining|Refining|Focusing|Sharpening|Clarifying)\b", re.MULTILINE),
    re.compile(
        r"^\s*(Goal|Approach|Synthesis|Draft|Refined|Step\s+\d+|Phase\s+\d+):", re.MULTILINE
    ),
]

# Advisor-name mentions in the body — the synthesis prompt explicitly
# forbids these. Case-insensitive word-boundary matches.
_ADVISOR_MENTION_RES = [
    re.compile(
        r"\b(ada|kai|mei|claude|gemini|chatgpt|the\s+advisors?|the\s+elders?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(the\s+debate|the\s+council|first\s+advisor|second\s+advisor)\b", re.IGNORECASE),
]

# CONVERGED tag leakage — explicitly banned by the prompt.
_CONVERGED_TAG_RE = re.compile(r"CONVERGED\s*:\s*(yes|no)", re.IGNORECASE)

# Mid-loop truncation heuristic: the last paragraph starts with a bolded
# header identical to a header used earlier. Strong signal of the
# Gemini-flash loop pattern (the model has cycled back to its first draft
# section and run out of output budget).


# ----------------------------------------------------------------------


class SynthesisValidator:
    """Runs the detection passes and reports the first violation found.

    The validator is biased toward specificity over sensitivity: each
    detector must have a low false-positive rate so the retry ceiling
    isn't hit on genuinely good output. Marginal cases (e.g. a synthesis
    that happens to include the word "ada" in a non-mention context)
    are accepted. The detectors fire only on patterns with high base-rate
    correlation with the observed failure modes.
    """

    # Repeated-header threshold: 3+ bolded headers triggers the loop
    # pathology detector. Two is tolerable (e.g. a list with headed items).
    REPEATED_HEADER_THRESHOLD = 3

    # Preamble is checked only on the first N characters — synthesis
    # outputs are often long, and a stray "okay" mid-body isn't preamble.
    PREAMBLE_WINDOW = 80

    def validate(self, text: str) -> SynthesisResult:
        stripped = text.strip()
        if not stripped:
            return SynthesisViolation(
                reason="empty_output",
                detail="The synthesiser returned empty output.",
            )

        # 1. Preamble at start (first-token-anchor failure).
        head = stripped[: self.PREAMBLE_WINDOW]
        if _PREAMBLE_RE.match(head):
            m = _PREAMBLE_RE.match(head)
            return SynthesisViolation(
                reason="preamble",
                detail=(
                    f"The synthesis starts with preamble ({m.group(0)!r}). "
                    "The instruction is to begin with the first word of the "
                    "answer itself."
                ),
            )

        # 2. CONVERGED tag leakage.
        if _CONVERGED_TAG_RE.search(text):
            m = _CONVERGED_TAG_RE.search(text)
            return SynthesisViolation(
                reason="converged_tag_leakage",
                detail=(
                    f"The synthesis contains a CONVERGED tag ({m.group(0)!r}). "
                    "Synthesis must not emit any convergence tag."
                ),
            )

        # 3. Repeated bolded-header CoT-loop pathology.
        headers = _BOLD_HEADER_RE.findall(text)
        if len(headers) >= self.REPEATED_HEADER_THRESHOLD:
            return SynthesisViolation(
                reason="cot_loop_headers",
                detail=(
                    f"The synthesis contains {len(headers)} bolded "
                    "section headers — this is the chain-of-thought "
                    "leakage signature (draft-mode output looping)."
                ),
            )

        # 4. Draft-label emission (Goal:/Approach:/Step 1: etc).
        for pat in _DRAFT_LABEL_RES:
            m = pat.search(text)
            if m:
                return SynthesisViolation(
                    reason="draft_label",
                    detail=(
                        f"The synthesis contains a draft-label line "
                        f"({m.group(0).strip()!r}) — reserved for "
                        "reasoning traces, not final output."
                    ),
                )

        # 5. Advisor-name mentions. Run the detectors but allow a small
        # number — the user may legitimately quote an advisor name in
        # rare contexts. Fire only on 2+ independent mentions.
        advisor_hits: list[str] = []
        for pat in _ADVISOR_MENTION_RES:
            advisor_hits.extend(m.group(0) for m in pat.finditer(text))
        if len(advisor_hits) >= 2:
            return SynthesisViolation(
                reason="advisor_mentions",
                detail=(
                    f"The synthesis mentions advisors/debate "
                    f"{len(advisor_hits)} times (e.g. {advisor_hits[:3]!r}). "
                    "The synthesis should not describe the debate."
                ),
            )

        # 6. Mid-loop truncation: the first bolded header reappears in
        # the last 200 chars. Combined with the repeated-header check
        # above, catches the specific Gemini-flash loop ending mid-
        # sentence.
        if headers:
            first_header = headers[0]
            tail = text[-200:]
            if first_header in tail and len(headers) >= 2:
                return SynthesisViolation(
                    reason="mid_loop_truncation",
                    detail=(
                        f"The synthesis appears to loop back to an earlier "
                        f"header ({first_header!r}) in its final lines — "
                        "a sign of mid-draft output budget exhaustion."
                    ),
                )

        return SynthesisOk()

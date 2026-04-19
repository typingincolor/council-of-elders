"""Parse a trailing `QUESTIONS: @elder text` block from an elder's reply.

Runs after ConvergencePolicy in DebateService so the CONVERGED tag is
already removed. Returns (cleaned_text, questions) where questions is a
tuple of ElderQuestion and cleaned_text has the entire QUESTIONS block
stripped. If no valid block is found, returns (raw, ()).

Rules:
- Looks for the last `QUESTIONS:` header followed by at least one valid
  `@elder text` line, where the block extends to end-of-input or a blank
  line.
- Only @claude / @gemini / @chatgpt are valid; unknown @-prefixed lines
  inside the block are tolerated as noise but not emitted.
- An elder's own self-directed question (@claude from claude) is dropped.
- If the block has no valid `@elder` lines, the whole input is returned
  unchanged with `()` — the header was a false positive.
- If the block isn't at the tail (non-blank content after the last
  `@elder` line of the block), treat as not a block and return unchanged.
"""

from __future__ import annotations

import re
from typing import get_args

from council.domain.models import ElderId, ElderQuestion

_HEADER_RE = re.compile(r"^\s*QUESTIONS\s*:\s*$", re.IGNORECASE)
_TAG_LINE_RE = re.compile(
    r"^\s*@(claude|gemini|chatgpt)\s+(.+?)\s*$",
    re.IGNORECASE,
)
_VALID_ELDERS: tuple[str, ...] = get_args(ElderId)


class QuestionParser:
    def parse(
        self,
        raw: str,
        *,
        from_elder: ElderId,
        round_number: int,
    ) -> tuple[str, tuple[ElderQuestion, ...]]:
        if not raw:
            return "", ()
        lines = raw.splitlines()
        # Find the last QUESTIONS: header.
        header_idx: int | None = None
        for i in range(len(lines) - 1, -1, -1):
            if _HEADER_RE.match(lines[i]):
                header_idx = i
                break
        if header_idx is None:
            return raw, ()

        # Check if there's any non-blank body content before the header.
        # If not, the block is not "at tail" of the body.
        has_body_before = any(lines[i].strip() for i in range(header_idx))
        if not has_body_before:
            return raw, ()

        # Read @elder lines after the header, up to blank line or EOF.
        last_question_idx = -1
        questions: list[ElderQuestion] = []
        for j in range(header_idx + 1, len(lines)):
            line = lines[j]
            if not line.strip():
                # Blank line terminates the block.
                break
            m = _TAG_LINE_RE.match(line)
            if not m:
                # Non-matching, non-blank line inside block — tolerate as
                # noise, but keep reading.
                continue
            target = m.group(1).lower()
            text = m.group(2).strip()
            if target == from_elder:
                continue  # drop self-directed
            if target not in _VALID_ELDERS:
                continue  # defensive
            last_question_idx = j
            questions.append(
                ElderQuestion(
                    from_elder=from_elder,
                    to_elder=target,  # type: ignore[arg-type]
                    text=text,
                    round_number=round_number,
                )
            )

        if not questions:
            return raw, ()

        # Find where the block ends (at the first blank line or EOF).
        block_end_idx = last_question_idx + 1
        if block_end_idx < len(lines) and not lines[block_end_idx].strip():
            # Next line after last question is blank; block ends there.
            block_end_idx += 1
        else:
            # No blank line found; block extends to EOF. Check for any
            # non-blank content after the last question (no blank line sep).
            for line in lines[block_end_idx:]:
                if line.strip():
                    return raw, ()

        # Reconstruct: body before header + body after block.
        cleaned = "\n".join(lines[:header_idx] + lines[block_end_idx:]).rstrip()
        return cleaned, tuple(questions)

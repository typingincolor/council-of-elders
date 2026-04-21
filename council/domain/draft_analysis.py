"""Draft analysis — find agreements and divergences across three R1s.

An interactive TUI helper used in ``r1_only`` mode. The user submits
a prompt, sees three independent drafts, and optionally presses ``d``
to get a structured comparison: what all three agree on, what they
diverge on, what's unique to each.

Deliberately uses one of the elders (the caller picks) rather than a
separate judge model so the TUI doesn't need additional wiring. The
task is summarisation, not preference — bias risk is lower than for
"pick the best" judging.
"""

from __future__ import annotations

from council.domain.models import Debate, ElderId, Message
from council.domain.ports import ElderPort

_ELDER_ORDER: tuple[ElderId, ElderId, ElderId] = ("ada", "kai", "mei")
_ELDER_DISPLAY: dict[ElderId, str] = {"ada": "Ada", "kai": "Kai", "mei": "Mei"}

DRAFT_ANALYSIS_PROMPT = """You will see three independent draft answers to the same prompt. Your job is to compare them.

Return a short markdown analysis with exactly these sections:

## Agreements
Points or claims all three drafts share, even if phrased differently. Bullet each one. If there are none, say "None material."

## Divergences
Substantive differences — different recommendations, different interpretations of the prompt, different framings. Bullet each one, naming which draft took which position. If there are none, say "None material."

## Unique to each
What's in one draft and not the others. Three sub-bullets: Ada, Kai, Mei. Be specific.

## Reading recommendation
One short paragraph: if the reader wanted a strong starting draft, which would you point them at first and why? If it depends on what they care about, say so and name the trade-off.

Rules:
- Be concise. A reader should scan this in under a minute.
- Quote specific language only when the exact wording is the point.
- Do not write a new draft. Do not synthesise. Do not pick a winner on "correctness" alone — surface the trade-offs.

User's prompt:
<<<
{prompt}
>>>

Draft 1 — Ada:
<<<
{draft_ada}
>>>

Draft 2 — Kai:
<<<
{draft_kai}
>>>

Draft 3 — Mei:
<<<
{draft_mei}
>>>
"""


def _r1_texts(debate: Debate) -> dict[ElderId, str]:
    if not debate.rounds:
        return {}
    r1 = debate.rounds[0]
    return {t.elder: (t.answer.text or "") for t in r1.turns}


async def analyze_drafts(debate: Debate, *, analyzer: ElderPort) -> str:
    """Ask one elder to compare the three R1 drafts. Returns markdown."""
    texts = _r1_texts(debate)
    prompt = DRAFT_ANALYSIS_PROMPT.format(
        prompt=debate.prompt.strip(),
        draft_ada=(texts.get("ada") or "").strip(),
        draft_kai=(texts.get("kai") or "").strip(),
        draft_mei=(texts.get("mei") or "").strip(),
    )
    return await analyzer.ask([Message("user", prompt)])


__all__ = [
    "DRAFT_ANALYSIS_PROMPT",
    "analyze_drafts",
]

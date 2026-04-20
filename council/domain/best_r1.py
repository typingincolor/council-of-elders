"""Best-R1 selection — LLM-judged.

Factored out of ``council/experiments/homogenisation/judges.py`` so the
headless pipeline (not just experiments) can use it. Under the
diversity-engine direction best-R1 is a mandatory baseline — every
debate where a judge is available records which elder's first-round
answer the judge considered strongest, and the deliverable compares
against it.

See ``docs/superpowers/plans/2026-04-20-diversity-engine-refactor.md``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from council.domain.models import Debate, ElderId, Message
from council.domain.ports import ElderPort

_ELDER_ORDER: tuple[ElderId, ElderId, ElderId] = ("ada", "kai", "mei")

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
_FENCE_RE = re.compile(r"^```[a-z]*\n?|\n?```$", re.MULTILINE)


@dataclass(frozen=True)
class BestR1Selection:
    elder: ElderId
    reason: str
    raw: str


class BestR1Selector(Protocol):
    async def select(self, debate: Debate) -> BestR1Selection | None: ...


@dataclass
class LLMJudgedBestR1Selector:
    judge_port: ElderPort

    async def select(self, debate: Debate) -> BestR1Selection | None:
        if not debate.rounds:
            return None
        r1 = debate.rounds[0]
        by_elder = {t.elder: (t.answer.text or "") for t in r1.turns}
        answers = tuple(by_elder.get(e, "") for e in _ELDER_ORDER)
        if not any(a.strip() for a in answers):
            return None
        prompt = BEST_R1_PROMPT.format(
            question=debate.prompt.strip(),
            answer_1=answers[0].strip(),
            answer_2=answers[1].strip(),
            answer_3=answers[2].strip(),
        )
        raw = await self.judge_port.ask([Message("user", prompt)])
        cleaned = _FENCE_RE.sub("", raw.strip())
        best_m = _BEST_RE.search(cleaned)
        reason_m = _REASON_RE.search(cleaned)
        best_idx = int(best_m.group(1)) - 1 if best_m else 0
        best_idx = max(0, min(2, best_idx))
        return BestR1Selection(
            elder=_ELDER_ORDER[best_idx],
            reason=reason_m.group(1).strip() if reason_m else "",
            raw=raw,
        )

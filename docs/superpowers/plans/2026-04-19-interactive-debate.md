# Interactive Debate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user take part in the debate (type messages between rounds that feed into subsequent elder prompts) and let elders pose structured questions to each other (via `QUESTIONS: @elder …` tail blocks), with all messages rendered inline in each elder's pane.

**Architecture:** Additive domain changes (two new value objects, one new event, one new parser, extended PromptBuilder + DebateService, extended JsonFileStore) plus primary-adapter TUI updates (Input → TextArea, event routing, pane rendering). Ports and vendor adapters unchanged.

**Tech Stack:** Python 3.12+, Textual (TextArea widget), pytest + pytest-asyncio, ruff.

**Reference spec:** `docs/superpowers/specs/2026-04-19-interactive-debate-design.md`

---

## Task 1: Domain value objects — UserMessage, ElderQuestion, Debate/Turn extensions

**Files:**
- Modify: `council/domain/models.py`
- Test: `tests/unit/test_models.py` (extend)

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_models.py`:

```python
from council.domain.models import UserMessage, ElderQuestion


class TestUserMessage:
    def test_construct_with_expected_fields(self):
        m = UserMessage(
            text="clarify scope please",
            after_round=1,
            created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
        )
        assert m.text == "clarify scope please"
        assert m.after_round == 1

    def test_is_frozen(self):
        m = UserMessage(
            text="x",
            after_round=0,
            created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
        )
        with pytest.raises(Exception):
            m.text = "y"  # type: ignore[misc]


class TestElderQuestion:
    def test_construct_with_expected_fields(self):
        q = ElderQuestion(
            from_elder="claude",
            to_elder="gemini",
            text="Have you considered X?",
            round_number=1,
        )
        assert q.from_elder == "claude"
        assert q.to_elder == "gemini"

    def test_is_frozen(self):
        q = ElderQuestion(
            from_elder="claude", to_elder="gemini", text="x", round_number=1
        )
        with pytest.raises(Exception):
            q.text = "y"  # type: ignore[misc]


class TestDebateUserMessages:
    def test_fresh_debate_has_empty_user_messages(self):
        pack = CouncilPack(name="bare", shared_context=None, personas={})
        d = Debate(
            id="d1",
            prompt="?",
            pack=pack,
            rounds=[],
            status="in_progress",
            synthesis=None,
        )
        assert d.user_messages == []


class TestTurnQuestions:
    def test_fresh_turn_has_empty_questions(self):
        t = Turn(
            elder="claude",
            answer=ElderAnswer(
                elder="claude",
                text="hi",
                error=None,
                agreed=True,
                created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
            ),
        )
        assert t.questions == ()

    def test_turn_with_questions(self):
        q = ElderQuestion(
            from_elder="claude", to_elder="gemini", text="?", round_number=1
        )
        t = Turn(
            elder="claude",
            answer=ElderAnswer(
                elder="claude",
                text="hi",
                error=None,
                agreed=True,
                created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
            ),
            questions=(q,),
        )
        assert len(t.questions) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_models.py -v -k "UserMessage or ElderQuestion or UserMessages or TurnQuestions"`
Expected: FAIL — `ImportError` on `UserMessage` and `ElderQuestion`.

- [ ] **Step 3: Extend `council/domain/models.py`**

Add below `ElderAnswer`:

```python
@dataclass(frozen=True)
class UserMessage:
    text: str
    after_round: int
    created_at: datetime


@dataclass(frozen=True)
class ElderQuestion:
    from_elder: ElderId
    to_elder: ElderId
    text: str
    round_number: int
```

Replace the existing `Turn` with:

```python
@dataclass(frozen=True)
class Turn:
    elder: ElderId
    answer: ElderAnswer
    questions: tuple[ElderQuestion, ...] = ()
```

Replace the existing `Debate` with (adding the `field` import at the top of the file if missing):

```python
@dataclass
class Debate:
    id: str
    prompt: str
    pack: CouncilPack
    rounds: list[Round]
    status: DebateStatus
    synthesis: ElderAnswer | None
    user_messages: list[UserMessage] = field(default_factory=list)
```

Add `from dataclasses import dataclass, field` to the imports at the top if only `dataclass` was imported.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_models.py -v`
Expected: all tests pass (previous + 6 new).

- [ ] **Step 5: Commit**

```bash
git add council/domain/models.py tests/unit/test_models.py
git commit -m "feat(domain): add UserMessage and ElderQuestion; extend Debate and Turn"
```

---

## Task 2: UserMessageReceived domain event

**Files:**
- Modify: `council/domain/events.py`
- Test: `tests/unit/test_events.py` (extend)

- [ ] **Step 1: Write failing test**

Append to `tests/unit/test_events.py`:

```python
from council.domain.events import UserMessageReceived
from council.domain.models import UserMessage


def test_user_message_received_carries_message():
    m = UserMessage(
        text="clarify please",
        after_round=1,
        created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
    )
    e = UserMessageReceived(message=m)
    assert e.message is m
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_events.py -v -k "user_message_received"`
Expected: FAIL — ImportError.

- [ ] **Step 3: Extend `council/domain/events.py`**

Add:

```python
from council.domain.models import UserMessage
```
to the imports (alongside existing ones).

Add this dataclass above the `DebateEvent` union:

```python
@dataclass(frozen=True)
class UserMessageReceived:
    message: UserMessage
```

Update the union:

```python
DebateEvent = Union[
    TurnStarted,
    TurnCompleted,
    TurnFailed,
    RoundCompleted,
    SynthesisCompleted,
    DebateAbandoned,
    UserMessageReceived,
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_events.py -v`
Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add council/domain/events.py tests/unit/test_events.py
git commit -m "feat(domain): add UserMessageReceived event"
```

---

## Task 3: QuestionParser

**Files:**
- Create: `council/domain/questions.py`
- Test: `tests/unit/test_question_parser.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_question_parser.py`:

```python
import pytest

from council.domain.questions import QuestionParser


@pytest.fixture
def parser():
    return QuestionParser()


class TestNoBlock:
    def test_no_questions_header_returns_raw_and_empty(self, parser):
        raw = "Here is my answer with no questions."
        cleaned, qs = parser.parse(raw, from_elder="claude", round_number=1)
        assert cleaned == raw
        assert qs == ()

    def test_empty_input(self, parser):
        cleaned, qs = parser.parse("", from_elder="claude", round_number=1)
        assert cleaned == ""
        assert qs == ()


class TestValidBlock:
    def test_single_question_extracted(self, parser):
        raw = (
            "My answer text.\n"
            "\n"
            "QUESTIONS:\n"
            "@gemini Have you considered timeline?"
        )
        cleaned, qs = parser.parse(raw, from_elder="claude", round_number=1)
        assert "QUESTIONS:" not in cleaned
        assert "@gemini" not in cleaned
        assert cleaned.strip() == "My answer text."
        assert len(qs) == 1
        assert qs[0].from_elder == "claude"
        assert qs[0].to_elder == "gemini"
        assert qs[0].text == "Have you considered timeline?"
        assert qs[0].round_number == 1

    def test_multiple_questions_extracted(self, parser):
        raw = (
            "Answer.\n"
            "QUESTIONS:\n"
            "@gemini Timeline?\n"
            "@chatgpt Growth?"
        )
        cleaned, qs = parser.parse(raw, from_elder="claude", round_number=2)
        assert cleaned.strip() == "Answer."
        assert len(qs) == 2
        assert {q.to_elder for q in qs} == {"gemini", "chatgpt"}

    def test_case_insensitive_header_and_elder(self, parser):
        raw = "Answer.\nquestions:\n@GEMINI Timeline?"
        cleaned, qs = parser.parse(raw, from_elder="claude", round_number=1)
        assert len(qs) == 1
        assert qs[0].to_elder == "gemini"


class TestMalformedOrUnknown:
    def test_unknown_elder_ignored(self, parser):
        raw = "Answer.\nQUESTIONS:\n@bob Ignore me\n@gemini Keep me"
        cleaned, qs = parser.parse(raw, from_elder="claude", round_number=1)
        # Unknown @bob line doesn't match and terminates the block; @gemini
        # after it is still expected to be captured because we read until a
        # blank line or end-of-input, tolerating unknown-but-@-prefixed lines
        # as "noise inside the block".
        assert len(qs) == 1
        assert qs[0].to_elder == "gemini"

    def test_self_directed_question_dropped(self, parser):
        raw = "Answer.\nQUESTIONS:\n@claude What about me?\n@gemini Real question?"
        cleaned, qs = parser.parse(raw, from_elder="claude", round_number=1)
        assert len(qs) == 1
        assert qs[0].to_elder == "gemini"

    def test_questions_header_without_valid_lines_yields_empty(self, parser):
        raw = "Answer.\nQUESTIONS:\n(no valid questions)"
        cleaned, qs = parser.parse(raw, from_elder="claude", round_number=1)
        # No @elder lines follow — treat as not-a-block; keep raw text.
        assert qs == ()
        assert cleaned == raw

    def test_block_terminates_at_blank_line(self, parser):
        raw = (
            "Answer.\n"
            "QUESTIONS:\n"
            "@gemini Real question?\n"
            "\n"
            "@chatgpt This is after the block and should stay in body"
        )
        cleaned, qs = parser.parse(raw, from_elder="claude", round_number=1)
        assert len(qs) == 1
        assert "should stay in body" in cleaned


class TestPositioning:
    def test_only_strips_when_block_is_at_tail(self, parser):
        raw = (
            "QUESTIONS:\n"
            "@gemini Early question\n"
            "\n"
            "But this is the real body."
        )
        cleaned, qs = parser.parse(raw, from_elder="claude", round_number=1)
        # The QUESTIONS block is not at the tail — keep raw, return ().
        assert qs == ()
        assert cleaned == raw
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_question_parser.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Implement `council/domain/questions.py`**

```python
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
- If the block isn't at the tail (trailing non-block content after the
  last `@elder` line that doesn't end in blank separator), treat as not
  a block and return unchanged.
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

        # Read @elder lines after the header, up to blank line or EOF.
        block_end = len(lines)
        questions: list[ElderQuestion] = []
        for j in range(header_idx + 1, len(lines)):
            line = lines[j]
            if not line.strip():
                block_end = j
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
            questions.append(
                ElderQuestion(
                    from_elder=from_elder,
                    to_elder=target,  # type: ignore[arg-type]
                    text=text,
                    round_number=round_number,
                )
            )
        else:
            block_end = len(lines)

        if not questions:
            return raw, ()

        # Verify the block is at the tail — after block_end, everything
        # must be blank.
        for line in lines[block_end:]:
            if line.strip():
                return raw, ()

        cleaned = "\n".join(lines[:header_idx]).rstrip()
        return cleaned, tuple(questions)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_question_parser.py -v`
Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add council/domain/questions.py tests/unit/test_question_parser.py
git commit -m "feat(domain): add QuestionParser for @elder-tagged question blocks"
```

---

## Task 4: PromptBuilder — user-messages section and questions-directed-at-you section

**Files:**
- Modify: `council/domain/prompting.py`
- Test: `tests/unit/test_prompting.py` (extend)

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_prompting.py`:

```python
from datetime import datetime as _dt
from council.domain.models import ElderQuestion, UserMessage


def _user_msg(text="clarify", after_round=1):
    return UserMessage(
        text=text,
        after_round=after_round,
        created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
    )


def _q(from_elder="claude", to_elder="gemini", text="why?", round_number=1):
    return ElderQuestion(
        from_elder=from_elder,
        to_elder=to_elder,
        text=text,
        round_number=round_number,
    )


class TestUserMessagesInPrompt:
    def test_round_1_omits_user_messages_section(self, builder):
        d = _debate()
        d.user_messages.append(_user_msg())
        prompt = builder.build(d, "claude", 1)
        # Round 1 has nothing to show; no prior round context.
        assert "You (the asker) said" not in prompt

    def test_round_2_includes_user_messages_section(self, builder):
        prev = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_answer("claude", "t1")),
                Turn(elder="gemini", answer=_answer("gemini", "t2")),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "t3")),
            ],
        )
        d = _debate(rounds=[prev])
        d.user_messages.append(_user_msg("focus on timeline", after_round=1))
        prompt = builder.build(d, "claude", 2)
        assert "You (the asker) said" in prompt
        assert "focus on timeline" in prompt
        assert "After round 1" in prompt

    def test_round_3_shows_all_prior_user_messages_in_order(self, builder):
        r1 = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_answer("claude", "t1")),
                Turn(elder="gemini", answer=_answer("gemini", "t2")),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "t3")),
            ],
        )
        r2 = Round(
            number=2,
            turns=[
                Turn(elder="claude", answer=_answer("claude", "u1")),
                Turn(elder="gemini", answer=_answer("gemini", "u2")),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "u3")),
            ],
        )
        d = _debate(rounds=[r1, r2])
        d.user_messages.append(_user_msg("first clarification", after_round=1))
        d.user_messages.append(_user_msg("second clarification", after_round=2))
        prompt = builder.build(d, "claude", 3)
        # Both messages present in order
        first = prompt.find("first clarification")
        second = prompt.find("second clarification")
        assert first != -1 and second != -1
        assert first < second


class TestDirectedQuestionsInPrompt:
    def test_questions_directed_at_target_elder_are_surfaced(self, builder):
        prev = Round(
            number=1,
            turns=[
                Turn(
                    elder="claude",
                    answer=_answer("claude", "t1"),
                    questions=(_q(from_elder="claude", to_elder="gemini",
                                  text="timeline?"),),
                ),
                Turn(elder="gemini", answer=_answer("gemini", "t2")),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "t3")),
            ],
        )
        d = _debate(rounds=[prev])
        gemini_prompt = builder.build(d, "gemini", 2)
        assert "Questions directed at you" in gemini_prompt
        assert "From Claude" in gemini_prompt
        assert "timeline?" in gemini_prompt

    def test_other_questions_between_advisors_are_listed_separately(self, builder):
        prev = Round(
            number=1,
            turns=[
                Turn(
                    elder="claude",
                    answer=_answer("claude", "t1"),
                    questions=(_q(from_elder="claude", to_elder="chatgpt",
                                  text="growth?"),),
                ),
                Turn(elder="gemini", answer=_answer("gemini", "t2")),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "t3")),
            ],
        )
        d = _debate(rounds=[prev])
        # From gemini's POV the Claude→ChatGPT question is "other"
        gemini_prompt = builder.build(d, "gemini", 2)
        assert "Questions directed at you" not in gemini_prompt
        assert "Other questions raised between advisors" in gemini_prompt
        assert "[ChatGPT" not in gemini_prompt  # gemini is the target; wait, it's Claude->ChatGPT
        assert "Claude" in gemini_prompt and "ChatGPT" in gemini_prompt
        assert "growth?" in gemini_prompt

    def test_prompt_asks_for_questions_block(self, builder):
        d = _debate()
        prompt = builder.build(d, "claude", 1)
        assert "QUESTIONS:" in prompt
        assert "@" in prompt  # the pattern example

    def test_synthesis_prompt_ignores_questions_and_user_messages(self, builder):
        # Synthesis prompt is already defined; adding user_messages or
        # questions to Debate must NOT change its shape (only the round
        # prompts are affected).
        r1 = Round(
            number=1,
            turns=[
                Turn(
                    elder="claude",
                    answer=_answer("claude", "t1"),
                    questions=(_q(from_elder="claude", to_elder="gemini",
                                  text="ignored in synth"),),
                ),
                Turn(elder="gemini", answer=_answer("gemini", "t2")),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "t3")),
            ],
        )
        d = _debate(rounds=[r1])
        d.user_messages.append(_user_msg("ignored user msg"))
        synth = builder.build_synthesis(d, by="claude")
        assert "QUESTIONS:" not in synth
        assert "You (the asker) said" not in synth
        assert "Questions directed at you" not in synth
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_prompting.py -v`
Expected: the new tests fail (AssertionError or similar).

- [ ] **Step 3: Extend `council/domain/prompting.py`**

Modify the `build` method to include the three new sections. The full updated file:

```python
from __future__ import annotations

from council.domain.models import Debate, ElderId, Round

_CONVERGED_INSTRUCTION = (
    "End your reply with exactly one of:\n"
    "CONVERGED: yes\n"
    "CONVERGED: no\n\n"
    "(Use CONVERGED: yes only if you would not change your answer after seeing "
    "what other advisors say.)"
)

_QUESTIONS_INSTRUCTION = (
    "If you have questions for another advisor, optionally include them "
    "BEFORE the CONVERGED line, as a block like this:\n\n"
    "QUESTIONS:\n"
    "@gemini your question here\n"
    "@chatgpt another question\n"
)

_ELDER_LABEL: dict[ElderId, str] = {
    "claude": "Claude",
    "gemini": "Gemini",
    "chatgpt": "ChatGPT",
}


class PromptBuilder:
    def build(self, debate: Debate, elder: ElderId, round_num: int) -> str:
        parts: list[str] = []
        header = self._header(debate, elder)
        if header:
            parts.append(header)
        parts.append(f"Question: {debate.prompt}")

        if round_num == 1:
            parts.append("Answer the question.")
            parts.append(_QUESTIONS_INSTRUCTION)
            parts.append(_CONVERGED_INSTRUCTION)
            return "\n\n".join(parts)

        # Round 2+
        own_prev = self._own_previous_answer(debate, elder, round_num)
        if own_prev is not None:
            parts.append(f"Your previous answer:\n{own_prev}")

        others = self._other_advisors_section(debate, elder, round_num)
        if others:
            parts.append(others)

        user_section = self._user_messages_section(debate)
        if user_section:
            parts.append(user_section)

        directed = self._directed_questions_section(debate, elder, round_num)
        if directed:
            parts.append(directed)

        other_qs = self._other_questions_section(debate, elder, round_num)
        if other_qs:
            parts.append(other_qs)

        parts.append(
            "You may revise your answer if their arguments change your view, "
            "or stand by it."
        )
        parts.append(_QUESTIONS_INSTRUCTION)
        parts.append(_CONVERGED_INSTRUCTION)
        return "\n\n".join(parts)

    def build_synthesis(self, debate: Debate, by: ElderId) -> str:
        parts: list[str] = []
        header = self._header(debate, by)
        if header:
            parts.append(header)
        parts.append(f"Original question: {debate.prompt}")
        parts.append(self._all_rounds_section(debate))
        parts.append(
            "You have seen every advisor's contribution across every round. "
            "Produce the final synthesised answer that best represents the "
            "consensus (or, where no consensus exists, your best judgment "
            "informed by the debate). Do not append a convergence tag."
        )
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    def _header(self, debate: Debate, elder: ElderId) -> str:
        lines: list[str] = []
        persona = debate.pack.personas.get(elder)
        if persona:
            lines.append(persona.strip())
        if debate.pack.shared_context:
            lines.append(debate.pack.shared_context.strip())
        return "\n\n".join(lines)

    def _own_previous_answer(
        self, debate: Debate, elder: ElderId, round_num: int
    ) -> str | None:
        prior = debate.rounds[round_num - 2]
        for t in prior.turns:
            if t.elder == elder and t.answer.text:
                return t.answer.text
        return None

    def _other_advisors_section(
        self, debate: Debate, elder: ElderId, round_num: int
    ) -> str:
        prior = debate.rounds[round_num - 2]
        lines = ["Other advisors said:"]
        for t in prior.turns:
            if t.elder == elder:
                continue
            if not t.answer.text:
                continue
            lines.append(f"[{_ELDER_LABEL[t.elder]}] {t.answer.text}")
        if len(lines) == 1:
            return ""
        return "\n".join(lines)

    def _user_messages_section(self, debate: Debate) -> str:
        if not debate.user_messages:
            return ""
        lines = ["You (the asker) said:"]
        for m in debate.user_messages:
            lines.append(f'After round {m.after_round}: "{m.text}"')
        return "\n".join(lines)

    def _directed_questions_section(
        self, debate: Debate, elder: ElderId, round_num: int
    ) -> str:
        prior = debate.rounds[round_num - 2]
        directed: list[str] = []
        for t in prior.turns:
            for q in t.questions:
                if q.to_elder == elder:
                    directed.append(
                        f'- From {_ELDER_LABEL[q.from_elder]}: "{q.text}"'
                    )
        if not directed:
            return ""
        return "Questions directed at you from the previous round:\n" + "\n".join(
            directed
        )

    def _other_questions_section(
        self, debate: Debate, elder: ElderId, round_num: int
    ) -> str:
        prior = debate.rounds[round_num - 2]
        others: list[str] = []
        for t in prior.turns:
            for q in t.questions:
                if q.to_elder == elder:
                    continue  # already surfaced in directed section
                others.append(
                    f'- [{_ELDER_LABEL[q.from_elder]} to '
                    f'{_ELDER_LABEL[q.to_elder]}]: "{q.text}"'
                )
        if not others:
            return ""
        return "Other questions raised between advisors:\n" + "\n".join(others)

    def _all_rounds_section(self, debate: Debate) -> str:
        chunks: list[str] = []
        for r in debate.rounds:
            chunks.append(f"--- Round {r.number} ---")
            for t in r.turns:
                if not t.answer.text:
                    continue
                chunks.append(f"[{_ELDER_LABEL[t.elder]}] {t.answer.text}")
        return "\n".join(chunks)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_prompting.py -v`
Expected: all passing (previous + the new user-message/question cases).

- [ ] **Step 5: Commit**

```bash
git add council/domain/prompting.py tests/unit/test_prompting.py
git commit -m "feat(domain): PromptBuilder surfaces user messages and peer questions"
```

---

## Task 5: DebateService — add_user_message and question parsing in run_round

**Files:**
- Modify: `council/domain/debate_service.py`
- Modify: `council/domain/events.py` — add `questions` field to `TurnCompleted`
- Test: `tests/unit/test_debate_service.py` (extend)
- Test: `tests/unit/test_events.py` (extend — TurnCompleted carries questions)

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_events.py`:

```python
def test_turn_completed_carries_questions_tuple():
    from council.domain.models import ElderAnswer, ElderQuestion
    ans = ElderAnswer(
        elder="claude", text="x", error=None, agreed=True,
        created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
    )
    q = ElderQuestion(
        from_elder="claude", to_elder="gemini", text="why?", round_number=1
    )
    e = TurnCompleted(
        elder="claude", round_number=1, answer=ans, questions=(q,)
    )
    assert e.questions == (q,)


def test_turn_completed_questions_default_empty():
    from council.domain.models import ElderAnswer
    ans = ElderAnswer(
        elder="claude", text="x", error=None, agreed=True,
        created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
    )
    e = TurnCompleted(elder="claude", round_number=1, answer=ans)
    assert e.questions == ()
```

Append to `tests/unit/test_debate_service.py`:

```python
from council.domain.events import UserMessageReceived
from council.domain.models import UserMessage


class TestAddUserMessage:
    async def test_appends_saves_and_publishes(self, svc):
        s, _ = svc
        d = _fresh_debate()
        # Run a round so user_messages.after_round = 1 makes sense
        await s.run_round(d)
        collected: list = []

        async def collect():
            async for ev in s.bus.subscribe():
                collected.append(ev)

        import asyncio
        task = asyncio.create_task(collect())
        await asyncio.sleep(0)
        msg = await s.add_user_message(d, "please focus on timeline")
        await asyncio.sleep(0)
        task.cancel()
        assert msg.text == "please focus on timeline"
        assert msg.after_round == 1
        assert d.user_messages == [msg]
        assert any(
            isinstance(ev, UserMessageReceived) and ev.message is msg
            for ev in collected
        )

    async def test_strips_whitespace(self, svc):
        s, _ = svc
        d = _fresh_debate()
        msg = await s.add_user_message(d, "   with space  \n")
        assert msg.text == "with space"


class TestRunRoundExtractsQuestions:
    async def test_questions_block_becomes_turn_questions(self, clock):
        elders = {
            "claude": FakeElder(
                elder_id="claude",
                replies=[
                    "My reply.\n\nQUESTIONS:\n@gemini Timeline?\n\nCONVERGED: no"
                ],
            ),
            "gemini": FakeElder(
                elder_id="gemini",
                replies=["Mine\nCONVERGED: yes"],
            ),
            "chatgpt": FakeElder(
                elder_id="chatgpt",
                replies=["Mine\nCONVERGED: yes"],
            ),
        }
        s = DebateService(
            elders=elders, store=InMemoryStore(), clock=clock, bus=InMemoryBus()
        )
        d = _fresh_debate()
        r = await s.run_round(d)
        claude_turn = next(t for t in r.turns if t.elder == "claude")
        assert len(claude_turn.questions) == 1
        assert claude_turn.questions[0].to_elder == "gemini"
        # cleaned text does not contain the QUESTIONS block
        assert "QUESTIONS" not in (claude_turn.answer.text or "")
        assert claude_turn.answer.text.strip() == "My reply."
```

Also, the fixture `svc` needs to expose the bus. Update the `svc` fixture at the top of `test_debate_service.py` to bind a shared bus:

```python
@pytest.fixture
def svc(clock):
    bus = InMemoryBus()
    elders = {
        "claude": FakeElder(elder_id="claude", replies=["Claude round-1\nCONVERGED: yes"]),
        "gemini": FakeElder(elder_id="gemini", replies=["Gemini round-1\nCONVERGED: no"]),
        "chatgpt": FakeElder(elder_id="chatgpt", replies=["ChatGPT round-1\nCONVERGED: yes"]),
    }
    service = DebateService(
        elders=elders,
        store=InMemoryStore(),
        clock=clock,
        bus=bus,
    )
    service.bus = bus  # expose for tests
    return service, elders
```

Note: `DebateService.bus` already exists as a field on the dataclass, so the `service.bus = bus` line is just re-emphasising the accessor. If it's already exposed, no change is needed — your implementation may skip the explicit re-bind.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_debate_service.py tests/unit/test_events.py -v -k "user_message or questions or add_user_message"`
Expected: FAIL — new methods and fields don't exist yet.

- [ ] **Step 3: Extend `council/domain/events.py`**

Change the `TurnCompleted` dataclass:

```python
@dataclass(frozen=True)
class TurnCompleted:
    elder: ElderId
    round_number: int
    answer: ElderAnswer
    questions: tuple["ElderQuestion", ...] = ()
```

Add the import at top of `events.py`:

```python
from council.domain.models import ElderAnswer, ElderError, ElderId, Round, UserMessage, ElderQuestion
```

- [ ] **Step 4: Extend `council/domain/debate_service.py`**

Add imports:

```python
from council.domain.events import (
    RoundCompleted,
    SynthesisCompleted,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
    UserMessageReceived,
)
from council.domain.models import (
    Debate,
    ElderAnswer,
    ElderError,
    ElderId,
    Round,
    Turn,
    UserMessage,
)
from council.domain.questions import QuestionParser
```

Extend the dataclass to own a parser:

```python
@dataclass
class DebateService:
    elders: dict[ElderId, ElderPort]
    store: TranscriptStore
    clock: Clock
    bus: EventBus
    prompt_builder: PromptBuilder = PromptBuilder()
    convergence: ConvergencePolicy = ConvergencePolicy()
    question_parser: QuestionParser = QuestionParser()
```

In `run_round`, modify the `_ask` inner function to parse questions after convergence. Replace:

```python
            cleaned, agreed = self.convergence.parse(raw)
            ans = ElderAnswer(
                elder=elder_id,
                text=cleaned,
                error=None,
                agreed=agreed,
                created_at=self.clock.now(),
            )
            await self.bus.publish(
                TurnCompleted(elder=elder_id, round_number=round_num, answer=ans)
            )
            return Turn(elder=elder_id, answer=ans)
```

with:

```python
            cleaned, agreed = self.convergence.parse(raw)
            cleaned_no_qs, questions = self.question_parser.parse(
                cleaned, from_elder=elder_id, round_number=round_num
            )
            ans = ElderAnswer(
                elder=elder_id,
                text=cleaned_no_qs,
                error=None,
                agreed=agreed,
                created_at=self.clock.now(),
            )
            await self.bus.publish(
                TurnCompleted(
                    elder=elder_id,
                    round_number=round_num,
                    answer=ans,
                    questions=questions,
                )
            )
            return Turn(elder=elder_id, answer=ans, questions=questions)
```

Add the new method:

```python
    async def add_user_message(self, debate: Debate, text: str) -> UserMessage:
        msg = UserMessage(
            text=text.strip(),
            after_round=len(debate.rounds),
            created_at=self.clock.now(),
        )
        debate.user_messages.append(msg)
        self.store.save(debate)
        await self.bus.publish(UserMessageReceived(message=msg))
        return msg
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/ -v`
Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add council/domain/debate_service.py council/domain/events.py tests/unit/test_debate_service.py tests/unit/test_events.py
git commit -m "feat(domain): DebateService.add_user_message; extract peer questions per turn"
```

---

## Task 6: JsonFileStore — serialise user_messages and turn.questions

**Files:**
- Modify: `council/adapters/storage/json_file.py`
- Test: `tests/unit/test_json_file_store.py` (extend)

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_json_file_store.py`:

```python
from council.domain.models import ElderQuestion, UserMessage


def test_round_trips_user_messages(tmp_path: Path):
    store = JsonFileStore(root=tmp_path)
    t = datetime(2026, 4, 19, tzinfo=timezone.utc)
    d = _debate()
    d.user_messages.append(UserMessage(text="clarify?", after_round=1, created_at=t))
    d.user_messages.append(UserMessage(text="follow up", after_round=2, created_at=t))
    store.save(d)
    loaded = store.load("d1")
    assert len(loaded.user_messages) == 2
    assert loaded.user_messages[0].text == "clarify?"
    assert loaded.user_messages[1].after_round == 2


def test_round_trips_turn_questions(tmp_path: Path):
    store = JsonFileStore(root=tmp_path)
    t = datetime(2026, 4, 19, tzinfo=timezone.utc)
    d = _debate()
    # Replace the existing round with one that has questions
    q = ElderQuestion(
        from_elder="claude", to_elder="gemini",
        text="timeline?", round_number=1
    )
    d.rounds[0].turns = [
        Turn(
            elder="claude",
            answer=ElderAnswer(
                elder="claude", text="ok", error=None, agreed=True, created_at=t
            ),
            questions=(q,),
        ),
        Turn(
            elder="gemini",
            answer=ElderAnswer(
                elder="gemini", text="yes", error=None, agreed=True, created_at=t
            ),
        ),
        Turn(
            elder="chatgpt",
            answer=ElderAnswer(
                elder="chatgpt", text="ok", error=None, agreed=True, created_at=t
            ),
        ),
    ]
    store.save(d)
    loaded = store.load("d1")
    claude_turn = next(
        t_ for t_ in loaded.rounds[0].turns if t_.elder == "claude"
    )
    assert len(claude_turn.questions) == 1
    assert claude_turn.questions[0].to_elder == "gemini"
    assert claude_turn.questions[0].text == "timeline?"


def test_load_legacy_debate_without_user_messages_key(tmp_path: Path):
    # Simulate a pre-v3 file without the new keys.
    path = tmp_path / "d1.json"
    path.write_text(
        '{"id":"d1","prompt":"?",'
        '"pack":{"name":"b","shared_context":null,"personas":{}},'
        '"rounds":[],"status":"in_progress","synthesis":null}',
        encoding="utf-8",
    )
    store = JsonFileStore(root=tmp_path)
    loaded = store.load("d1")
    assert loaded.user_messages == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_json_file_store.py -v`
Expected: new tests FAIL.

- [ ] **Step 3: Extend serialiser/deserialiser in `council/adapters/storage/json_file.py`**

Replace `_serialize_debate`:

```python
def _serialize_debate(d: Debate) -> dict[str, Any]:
    return {
        "id": d.id,
        "prompt": d.prompt,
        "pack": _serialize_pack(d.pack),
        "rounds": [_serialize_round(r) for r in d.rounds],
        "status": d.status,
        "synthesis": _serialize_answer(d.synthesis) if d.synthesis else None,
        "user_messages": [_serialize_user_message(m) for m in d.user_messages],
    }


def _serialize_user_message(m: "UserMessage") -> dict[str, Any]:
    return {
        "text": m.text,
        "after_round": m.after_round,
        "created_at": m.created_at.isoformat(),
    }
```

Replace `_serialize_round`:

```python
def _serialize_round(r: Round) -> dict[str, Any]:
    return {
        "number": r.number,
        "turns": [
            {
                "elder": t.elder,
                "answer": _serialize_answer(t.answer),
                "questions": [_serialize_question(q) for q in t.questions],
            }
            for t in r.turns
        ],
    }


def _serialize_question(q: "ElderQuestion") -> dict[str, Any]:
    return {
        "from_elder": q.from_elder,
        "to_elder": q.to_elder,
        "text": q.text,
        "round_number": q.round_number,
    }
```

Replace `_deserialize_debate`:

```python
def _deserialize_debate(d: dict[str, Any]) -> Debate:
    debate = Debate(
        id=d["id"],
        prompt=d["prompt"],
        pack=_deserialize_pack(d["pack"]),
        rounds=[_deserialize_round(r) for r in d["rounds"]],
        status=d["status"],
        synthesis=_deserialize_answer(d["synthesis"]) if d["synthesis"] else None,
    )
    for m in d.get("user_messages", []):
        debate.user_messages.append(_deserialize_user_message(m))
    return debate


def _deserialize_user_message(m: dict[str, Any]) -> "UserMessage":
    return UserMessage(
        text=m["text"],
        after_round=m["after_round"],
        created_at=datetime.fromisoformat(m["created_at"]),
    )
```

Replace `_deserialize_round`:

```python
def _deserialize_round(r: dict[str, Any]) -> Round:
    return Round(
        number=r["number"],
        turns=[
            Turn(
                elder=t["elder"],
                answer=_deserialize_answer(t["answer"]),
                questions=tuple(
                    _deserialize_question(q) for q in t.get("questions", [])
                ),
            )
            for t in r["turns"]
        ],
    )


def _deserialize_question(q: dict[str, Any]) -> "ElderQuestion":
    return ElderQuestion(
        from_elder=q["from_elder"],
        to_elder=q["to_elder"],
        text=q["text"],
        round_number=q["round_number"],
    )
```

Add the new imports at the top:

```python
from council.domain.models import (
    CouncilPack,
    Debate,
    ElderAnswer,
    ElderError,
    ElderQuestion,
    ElderId,
    Round,
    Turn,
    UserMessage,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_json_file_store.py -v`
Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add council/adapters/storage/json_file.py tests/unit/test_json_file_store.py
git commit -m "feat(adapters): persist user_messages and per-turn questions in JsonFileStore"
```

---

## Task 7: TUI — replace Input with TextArea, wire Ctrl+Enter submit

**Files:**
- Modify: `council/app/tui/app.py`
- Modify: `tests/e2e/test_tui_full_debate.py` (adjust press sequence)
- Modify: `tests/e2e/test_tui_tab_navigation.py` (adjust press sequence)

- [ ] **Step 1: Update `council/app/tui/app.py`**

Replace the `Input` widget with `TextArea`. Changes:

Replace the import line:

```python
from textual.widgets import Footer, Header, Input, RichLog, Static
```

with:

```python
from textual.widgets import Footer, Header, RichLog, Static, TextArea
```

Replace the CSS block:

```python
    CSS = """
    #notices { height: auto; max-height: 6; padding: 0 1; }
    #view { height: 1fr; }
    #input { dock: bottom; }
    """
```

with:

```python
    CSS = """
    #notices { height: auto; max-height: 6; padding: 0 1; }
    #view { height: 1fr; }
    #input { dock: bottom; min-height: 3; max-height: 8; }
    """
```

Replace the `compose` method body's input line:

```python
        yield Input(placeholder="Ask the council…", id="input")
```

with:

```python
        yield TextArea(id="input")
```

Replace `on_mount`'s focus target — no change, still `self.query_one("#input", TextArea).focus()`. Update the type:

```python
    async def on_mount(self) -> None:
        self._stream_task = self._spawn(self._consume_events())
        self.query_one("#input", TextArea).focus()
        self._spawn(self._run_health_checks())
```

Replace the `@on(Input.Submitted, "#input")` handler. `TextArea` doesn't have a `Submitted` event; we need a custom key binding. Add a `BINDINGS` entry and an `action_` method, AND a key handler on the TextArea itself using a subclass or a key-intercept on_key.

Simplest approach: subclass `TextArea` to emit a message on `ctrl+enter`:

Add above `CouncilApp`:

```python
from textual.message import Message


class CouncilInput(TextArea):
    class Submitted(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    BINDINGS = [Binding("ctrl+enter", "submit", "Submit", show=False)]

    def action_submit(self) -> None:
        self.post_message(self.Submitted(self.text))
```

Then in `CouncilApp.compose`:

```python
        yield CouncilInput(id="input")
```

And replace the handler:

```python
    @on(CouncilInput.Submitted, "#input")
    async def _on_input_submitted(self, event: CouncilInput.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        input_widget = self.query_one("#input", CouncilInput)
        input_widget.clear()  # TextArea.clear() wipes content
        if self._debate is None:
            # First submission — use as the initial prompt.
            pack = self._pack_loader.load(self._pack_name)
            self._debate = Debate(
                id=str(uuid.uuid4()),
                prompt=text,
                pack=pack,
                rounds=[],
                status="in_progress",
                synthesis=None,
            )
            input_widget.disabled = True
            self._view.focus()
            self._spawn(self._service.run_round(self._debate))
        else:
            # Between-round user message.
            if not self.awaiting_decision:
                return
            self._spawn(self._service.add_user_message(self._debate, text))
```

Remove the old `_on_prompt_submitted` method (the block starting with the `@on(Input.Submitted, "#input")` decorator).

Update `action_continue_round` to re-enable the input when a new round starts isn't needed — we want the input disabled DURING the round and enabled again when the round ends. Add re-enable logic in `_consume_events`:

```python
    async def _consume_events(self) -> None:
        async for ev in self._bus.subscribe():
            if isinstance(ev, TurnStarted):
                self._view.pane(ev.elder).begin_thinking(ev.round_number)
            elif isinstance(ev, TurnCompleted):
                self._view.pane(ev.elder).end_thinking_completed(ev.answer)
            elif isinstance(ev, TurnFailed):
                self._view.pane(ev.elder).end_thinking_failed(ev.error)
            elif isinstance(ev, RoundCompleted):
                self.awaiting_decision = True
                # Re-enable the input so the user can type a follow-up.
                self.query_one("#input", CouncilInput).disabled = False
            elif isinstance(ev, SynthesisCompleted):
                self._view.pane("synthesis").end_thinking_completed(ev.answer)
                self._view.pane("synthesis").focus()
                self.is_finished = True
                self.awaiting_decision = False
            elif isinstance(ev, UserMessageReceived):
                # Dispatch to all three elder panes for inline rendering.
                for pane_key in ("claude", "gemini", "chatgpt"):
                    self._view.pane(pane_key).on_user_message(ev.message)
```

Also update `action_continue_round` to disable the input when starting a new round:

```python
    async def action_continue_round(self) -> None:
        if not self.awaiting_decision or self._debate is None:
            return
        self.awaiting_decision = False
        self.query_one("#input", CouncilInput).disabled = True
        self._spawn(self._service.run_round(self._debate))
```

Add the import for the new event at the top:

```python
from council.domain.events import (
    RoundCompleted,
    SynthesisCompleted,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
    UserMessageReceived,
)
```

- [ ] **Step 2: Update e2e tests to submit via Ctrl+Enter**

In `tests/e2e/test_tui_full_debate.py`, change:

```python
        await pilot.press(*"What should I do?")
        await pilot.press("enter")
```

to:

```python
        await pilot.press(*"What should I do?")
        await pilot.press("ctrl+enter")
```

In `tests/e2e/test_tui_tab_navigation.py`, change:

```python
        await pilot.press(*"Any question")
        await pilot.press("enter")
```

to:

```python
        await pilot.press(*"Any question")
        await pilot.press("ctrl+enter")
```

In `tests/e2e/test_tui_history_per_elder.py`, change:

```python
        await pilot.press(*"Two rounds?")
        await pilot.press("enter")
```

to:

```python
        await pilot.press(*"Two rounds?")
        await pilot.press("ctrl+enter")
```

- [ ] **Step 3: Run tests**

Run: `pytest --tb=short -q`
Expected: all previously-passing tests still green.

- [ ] **Step 4: Commit**

```bash
git add council/app/tui/app.py tests/e2e/test_tui_full_debate.py tests/e2e/test_tui_tab_navigation.py tests/e2e/test_tui_history_per_elder.py
git commit -m "feat(tui): replace Input with multi-line TextArea; Ctrl+Enter submits"
```

---

## Task 8: ElderPaneWidget — render user messages and peer questions inline

**Files:**
- Modify: `council/app/tui/elder_pane.py`
- Modify: `council/app/tui/app.py` (event wiring)
- Test: `tests/e2e/test_elder_pane_widget.py` (extend)

- [ ] **Step 1: Write failing tests**

Append to `tests/e2e/test_elder_pane_widget.py`:

```python
from council.domain.models import ElderQuestion, UserMessage


async def test_widget_renders_user_message_inline():
    clock = FakeClock(now=datetime(2026, 4, 19, 12, tzinfo=timezone.utc))
    widget = ElderPaneWidget(
        elder_id="claude",
        display_name="Claude",
        verb_chooser=FixedVerbChooser("Pondering"),
        clock=clock,
    )
    async with _Host(widget).run_test() as pilot:
        await pilot.pause()
        widget.begin_thinking(1)
        widget.end_thinking_completed(_answer(text="R1 answer"))
        await pilot.pause()
        widget.on_user_message(
            UserMessage(
                text="please clarify scope",
                after_round=1,
                created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
            )
        )
        await pilot.pause()
        history = widget.history_text()
        assert "R1 answer" in history
        assert "please clarify scope" in history
        assert "You" in history  # rendered as [You after round 1] ...


async def test_widget_renders_asker_question_in_asker_pane():
    """Claude's pane shows Claude's own outgoing questions as '[To Gemini] …'."""
    clock = FakeClock(now=datetime(2026, 4, 19, 12, tzinfo=timezone.utc))
    widget = ElderPaneWidget(
        elder_id="claude",
        display_name="Claude",
        verb_chooser=FixedVerbChooser("Pondering"),
        clock=clock,
    )
    async with _Host(widget).run_test() as pilot:
        await pilot.pause()
        widget.begin_thinking(1)
        q = ElderQuestion(
            from_elder="claude", to_elder="gemini",
            text="timeline?", round_number=1
        )
        widget.end_thinking_completed(
            _answer(text="My answer"), questions=(q,)
        )
        await pilot.pause()
        history = widget.history_text()
        assert "My answer" in history
        assert "To Gemini" in history
        assert "timeline?" in history


async def test_widget_renders_incoming_question_in_target_pane():
    """Gemini's pane shows Claude's question TO Gemini as '[From Claude] …'."""
    clock = FakeClock(now=datetime(2026, 4, 19, 12, tzinfo=timezone.utc))
    widget = ElderPaneWidget(
        elder_id="gemini",
        display_name="Gemini",
        verb_chooser=FixedVerbChooser("Pondering"),
        clock=clock,
    )
    async with _Host(widget).run_test() as pilot:
        await pilot.pause()
        q = ElderQuestion(
            from_elder="claude", to_elder="gemini",
            text="timeline?", round_number=1
        )
        widget.on_incoming_question(q)
        await pilot.pause()
        history = widget.history_text()
        assert "From Claude" in history
        assert "timeline?" in history
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/e2e/test_elder_pane_widget.py -v`
Expected: FAIL — methods `on_user_message`, `on_incoming_question`, and the `questions=` kwarg on `end_thinking_completed` don't exist.

- [ ] **Step 3: Extend `council/app/tui/elder_pane.py` ElderPaneWidget**

Modify `end_thinking_completed` to accept questions:

```python
    def end_thinking_completed(
        self,
        answer: ElderAnswer,
        questions: tuple["ElderQuestion", ...] = (),
    ) -> None:
        super().end_thinking_completed(answer)
        self._clear_thinking_line()
        self._append_completed(answer)
        # Render the asker's own outgoing questions below the answer.
        for q in questions:
            self._append_to_line(f'[dim][To {_display(q.to_elder)}][/] {q.text}')
        self.label_text = self.current_label()
```

Add the new methods and helpers (near the bottom of the class):

```python
    def on_user_message(self, message: "UserMessage") -> None:
        self._append_to_line(
            f'[dim][You after round {message.after_round}][/] {message.text}'
        )

    def on_incoming_question(self, question: "ElderQuestion") -> None:
        self._append_to_line(
            f'[dim][From {_display(question.from_elder)}][/] {question.text}'
        )

    def _append_to_line(self, line: str) -> None:
        self._history_buffer.append(line)
        self.query_one("#pane-history", RichLog).write(line)
```

Add `_display` helper + import `UserMessage`, `ElderQuestion` at top of the file:

```python
from council.domain.models import ElderAnswer, ElderError, ElderId, ElderQuestion, UserMessage


_DISPLAY_NAMES: dict[str, str] = {
    "claude": "Claude",
    "gemini": "Gemini",
    "chatgpt": "ChatGPT",
}


def _display(elder: str) -> str:
    return _DISPLAY_NAMES.get(elder, elder)
```

- [ ] **Step 4: Update `council/app/tui/app.py` to route incoming questions**

In `_consume_events`, extend the `TurnCompleted` branch:

```python
            elif isinstance(ev, TurnCompleted):
                self._view.pane(ev.elder).end_thinking_completed(
                    ev.answer, questions=ev.questions
                )
                # Fan each outgoing question into the TARGET elder's pane.
                for q in ev.questions:
                    self._view.pane(q.to_elder).on_incoming_question(q)
```

- [ ] **Step 5: Run tests**

Run: `pytest --tb=short -q`
Expected: all tests pass (existing + 3 new).

- [ ] **Step 6: Commit**

```bash
git add council/app/tui/elder_pane.py council/app/tui/app.py tests/e2e/test_elder_pane_widget.py
git commit -m "feat(tui): render user messages and peer questions inline in each pane"
```

---

## Task 9: E2E — user message between rounds

**Files:**
- Create: `tests/e2e/test_tui_user_messages.py`

- [ ] **Step 1: Write the test**

```python
import asyncio
from datetime import datetime, timezone

from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.in_memory import InMemoryStore
from council.app.tui.app import CouncilApp
from tests.e2e.conftest import pane_lines


async def _wait_until(pilot, predicate, *, timeout_s=5.0, tick=0.05):
    elapsed = 0.0
    while not predicate():
        await pilot.pause()
        await asyncio.sleep(tick)
        elapsed += tick
        if elapsed > timeout_s:
            raise AssertionError(f"Timed out; elapsed={elapsed:.2f}s")


async def test_user_message_appears_in_all_elder_panes(tmp_path):
    (tmp_path / "bare").mkdir()
    elders = {
        "claude": FakeElder(
            elder_id="claude",
            replies=["R1 c\nCONVERGED: no", "R2 c\nCONVERGED: yes"],
        ),
        "gemini": FakeElder(
            elder_id="gemini",
            replies=["R1 g\nCONVERGED: no", "R2 g\nCONVERGED: yes"],
        ),
        "chatgpt": FakeElder(
            elder_id="chatgpt",
            replies=["R1 x\nCONVERGED: no", "R2 x\nCONVERGED: yes"],
        ),
    }
    app = CouncilApp(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 19, tzinfo=timezone.utc)),
        pack_loader=FilesystemPackLoader(root=tmp_path),
        pack_name="bare",
    )
    async with app.run_test() as pilot:
        await pilot.press(*"Initial question")
        await pilot.press("ctrl+enter")
        await _wait_until(pilot, lambda: app.awaiting_decision)

        # Type a user message and submit.
        # Input is re-enabled at awaiting_decision; focus it first.
        app.query_one("#input").focus()
        await pilot.press(*"please focus on timeline")
        await pilot.press("ctrl+enter")
        await pilot.pause()

        # Assert the user message appears in all three elder panes.
        for elder in ("claude", "gemini", "chatgpt"):
            text = pane_lines(app, elder)
            assert "please focus on timeline" in text
            assert "You after round 1" in text
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/e2e/test_tui_user_messages.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_tui_user_messages.py
git commit -m "test(tui): e2e for user message appearing in all elder panes"
```

---

## Task 10: E2E — elder-to-elder question

**Files:**
- Create: `tests/e2e/test_tui_elder_questions.py`

- [ ] **Step 1: Write the test**

```python
import asyncio
from datetime import datetime, timezone

from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.in_memory import InMemoryStore
from council.app.tui.app import CouncilApp
from tests.e2e.conftest import pane_lines


async def _wait_until(pilot, predicate, *, timeout_s=5.0, tick=0.05):
    elapsed = 0.0
    while not predicate():
        await pilot.pause()
        await asyncio.sleep(tick)
        elapsed += tick
        if elapsed > timeout_s:
            raise AssertionError(f"Timed out; elapsed={elapsed:.2f}s")


async def test_elder_question_surfaces_in_both_asker_and_target_panes(tmp_path):
    (tmp_path / "bare").mkdir()
    elders = {
        "claude": FakeElder(
            elder_id="claude",
            replies=[
                "My answer.\n\nQUESTIONS:\n@gemini Timeline?\n\nCONVERGED: no"
            ],
        ),
        "gemini": FakeElder(elder_id="gemini", replies=["mine\nCONVERGED: no"]),
        "chatgpt": FakeElder(elder_id="chatgpt", replies=["mine\nCONVERGED: no"]),
    }
    app = CouncilApp(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 19, tzinfo=timezone.utc)),
        pack_loader=FilesystemPackLoader(root=tmp_path),
        pack_name="bare",
    )
    async with app.run_test() as pilot:
        await pilot.press(*"Go")
        await pilot.press("ctrl+enter")
        await _wait_until(pilot, lambda: app.awaiting_decision)

        # Claude's pane should show the outgoing question.
        claude_text = pane_lines(app, "claude")
        assert "To Gemini" in claude_text
        assert "Timeline?" in claude_text

        # Gemini's pane should show the incoming question.
        gemini_text = pane_lines(app, "gemini")
        assert "From Claude" in gemini_text
        assert "Timeline?" in gemini_text

        # ChatGPT's pane should NOT show this question (not directed at it).
        chatgpt_text = pane_lines(app, "chatgpt")
        assert "Timeline?" not in chatgpt_text
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/e2e/test_tui_elder_questions.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_tui_elder_questions.py
git commit -m "test(tui): e2e for elder-to-elder question routing to correct panes"
```

---

## Task 11: Polish — ruff, full suite, README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run ruff**

```bash
source .venv/bin/activate
ruff check council/ tests/ --fix
ruff format council/ tests/
```

- [ ] **Step 2: Run full test suite**

Run: `pytest -v`
Expected: all passing.

- [ ] **Step 3: Update README**

In `README.md`, find the keybindings section. Add above the table (or as a sibling section) a short note:

```markdown
### Participating in the debate

Between rounds, the input at the bottom is re-enabled. Type a clarifying question or comment and press **Ctrl+Enter** to send it to the elders — they'll see it in the next round's prompt. Plain **Enter** just inserts a newline so you can write longer messages.

Elders can also pose questions to each other by ending their reply with a block like:

\`\`\`
QUESTIONS:
@gemini Have you considered the timeline impact?
@chatgpt What about the growth tradeoff?
\`\`\`

When that happens, the question appears labelled `[To Gemini]` in the asker's pane and `[From Claude]` in the target's pane, and the target gets a "Questions directed at you" section in its next prompt.
```

- [ ] **Step 4: Commit**

```bash
git add README.md council/ tests/
git commit -m "docs: describe interactive debate features in README"
```

- [ ] **Step 5: Push**

```bash
git push
```

---

## Spec coverage audit

| Spec section | Covered by |
|---|---|
| UserMessage + ElderQuestion value objects | Task 1 |
| Debate.user_messages + Turn.questions | Task 1 |
| UserMessageReceived event | Task 2 |
| QuestionParser (parallel to ConvergencePolicy) | Task 3 |
| PromptBuilder: "You said" + directed + other questions sections | Task 4 |
| QUESTIONS instruction in outgoing prompt | Task 4 |
| Synthesis prompt ignores user_messages + questions | Task 4 |
| DebateService.add_user_message (persist + publish) | Task 5 |
| run_round parses questions, populates Turn.questions, emits in TurnCompleted | Task 5 |
| TurnCompleted extended with questions field | Task 5 |
| JsonFileStore serialises user_messages + turn.questions, backward-compatible load | Task 6 |
| TextArea replacing Input with Ctrl+Enter submit | Task 7 |
| Initial prompt vs follow-up distinction | Task 7 |
| Input disable during rounds, re-enable on RoundCompleted | Task 7 |
| Bus routing UserMessageReceived to all elder panes | Task 7 |
| ElderPaneWidget.on_user_message (inline render) | Task 8 |
| ElderPaneWidget.on_incoming_question (target pane render) | Task 8 |
| Asker pane renders own outgoing questions | Task 8 |
| E2E: user message appears in all panes | Task 9 |
| E2E: elder question appears in asker and target panes only | Task 10 |
| Tests: edited existing e2e to use ctrl+enter | Task 7 |

No gaps.

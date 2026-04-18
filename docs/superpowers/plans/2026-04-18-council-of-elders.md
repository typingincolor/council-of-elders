# Council of Elders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Textual TUI that runs a user-controlled, convergence-based debate across Claude Code, Gemini CLI, and Codex CLI (using the user's existing paid subscriptions — no API costs), then produces a single synthesized answer.

**Architecture:** Hexagonal (ports & adapters). Pure domain core (`council.domain`) that never imports from Textual, asyncio subprocess, or any adapter module. Driving adapters: Textual TUI + headless CLI. Driven adapters: per-vendor CLI adapters + JSON persistence + filesystem pack loader. `FakeElder` is shipped in the package for reuse by integration tests and demos.

**Tech Stack:** Python 3.12+, Textual (TUI), pytest + pytest-asyncio, `asyncio.create_subprocess_exec` for vendor CLI invocation, `uv` for dependency management, ruff for linting.

**Reference spec:** `docs/superpowers/specs/2026-04-18-council-of-elders-design.md`

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `README.md`
- Create: `council/__init__.py`
- Create: `council/domain/__init__.py`
- Create: `council/adapters/__init__.py`
- Create: `council/adapters/elders/__init__.py`
- Create: `council/adapters/storage/__init__.py`
- Create: `council/adapters/packs/__init__.py`
- Create: `council/adapters/bus/__init__.py`
- Create: `council/adapters/clock/__init__.py`
- Create: `council/app/__init__.py`
- Create: `council/app/tui/__init__.py`
- Create: `council/app/headless/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/contract/__init__.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/e2e/__init__.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "council-of-elders"
version = "0.1.0"
description = "A TUI that orchestrates a debate across Claude, Gemini, and ChatGPT using their vendor CLIs."
requires-python = ">=3.12"
dependencies = [
    "textual>=0.85",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "ruff>=0.6",
]

[project.scripts]
council = "council.app.tui.app:main"
council-headless = "council.app.headless.main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "integration: requires real vendor CLIs to be installed and authenticated",
]
addopts = "-m 'not integration'"

[tool.ruff]
line-length = 100
target-version = "py312"
```

- [ ] **Step 2: Write `.gitignore`**

```
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
.ruff_cache/
dist/
build/
*.egg-info/
.coverage
~/.council/
```

- [ ] **Step 3: Write a one-line `README.md`**

```markdown
# Council of Elders

A TUI that orchestrates a debate across Claude Code, Gemini CLI, and Codex CLI using your existing paid subscriptions.
```

- [ ] **Step 4: Create all `__init__.py` files (each empty)**

Run from the project root:

```bash
touch council/__init__.py \
      council/domain/__init__.py \
      council/adapters/__init__.py \
      council/adapters/elders/__init__.py \
      council/adapters/storage/__init__.py \
      council/adapters/packs/__init__.py \
      council/adapters/bus/__init__.py \
      council/adapters/clock/__init__.py \
      council/app/__init__.py \
      council/app/tui/__init__.py \
      council/app/headless/__init__.py \
      tests/__init__.py \
      tests/unit/__init__.py \
      tests/contract/__init__.py \
      tests/integration/__init__.py \
      tests/e2e/__init__.py
```

- [ ] **Step 5: Install and verify**

```bash
uv venv && source .venv/bin/activate
uv pip install -e '.[dev]'
pytest --collect-only
```

Expected: no tests collected (none exist yet), exit code 0.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore README.md council/ tests/
git commit -m "chore: scaffold project structure"
```

---

## Task 2: Domain models

**Files:**
- Create: `council/domain/models.py`
- Test: `tests/unit/test_models.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_models.py`:

```python
from datetime import datetime, timezone
import pytest
from council.domain.models import (
    CouncilPack,
    Debate,
    ElderAnswer,
    ElderError,
    Round,
    Turn,
)


def _answer(elder="claude", agreed=None, text="hello", error=None):
    return ElderAnswer(
        elder=elder,
        text=text,
        error=error,
        agreed=agreed,
        created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )


class TestRound:
    def test_converged_true_when_three_elders_all_agreed(self):
        r = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_answer("claude", agreed=True)),
                Turn(elder="gemini", answer=_answer("gemini", agreed=True)),
                Turn(elder="chatgpt", answer=_answer("chatgpt", agreed=True)),
            ],
        )
        assert r.converged() is True

    def test_converged_false_when_any_disagreed(self):
        r = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_answer("claude", agreed=True)),
                Turn(elder="gemini", answer=_answer("gemini", agreed=False)),
                Turn(elder="chatgpt", answer=_answer("chatgpt", agreed=True)),
            ],
        )
        assert r.converged() is False

    def test_converged_false_when_any_undeclared(self):
        r = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_answer("claude", agreed=True)),
                Turn(elder="gemini", answer=_answer("gemini", agreed=None)),
                Turn(elder="chatgpt", answer=_answer("chatgpt", agreed=True)),
            ],
        )
        assert r.converged() is False

    def test_converged_false_with_fewer_than_three_turns(self):
        r = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_answer("claude", agreed=True)),
                Turn(elder="gemini", answer=_answer("gemini", agreed=True)),
            ],
        )
        assert r.converged() is False


class TestCouncilPack:
    def test_empty_pack_has_no_overrides(self):
        pack = CouncilPack(name="bare", shared_context=None, personas={})
        assert pack.personas == {}
        assert pack.shared_context is None


class TestElderAnswer:
    def test_can_hold_only_error(self):
        err = ElderError(elder="claude", kind="timeout", detail="")
        a = _answer(error=err, text=None)
        assert a.text is None
        assert a.error is err


class TestDebate:
    def test_new_debate_has_no_rounds(self):
        pack = CouncilPack(name="bare", shared_context=None, personas={})
        d = Debate(id="abc", prompt="hi", pack=pack, rounds=[], status="in_progress", synthesis=None)
        assert d.rounds == []
        assert d.status == "in_progress"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/unit/test_models.py -v
```

Expected: ImportError / ModuleNotFoundError on `council.domain.models`.

- [ ] **Step 3: Implement `council/domain/models.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ElderId = Literal["claude", "gemini", "chatgpt"]
ErrorKind = Literal[
    "timeout",
    "cli_missing",
    "auth_failed",
    "nonzero_exit",
    "unparseable",
]
DebateStatus = Literal["in_progress", "synthesized", "abandoned"]


@dataclass(frozen=True)
class ElderError:
    elder: ElderId
    kind: ErrorKind
    detail: str


@dataclass(frozen=True)
class ElderAnswer:
    elder: ElderId
    text: str | None
    error: ElderError | None
    agreed: bool | None
    created_at: datetime


@dataclass(frozen=True)
class Turn:
    elder: ElderId
    answer: ElderAnswer


@dataclass
class Round:
    number: int
    turns: list[Turn]

    def converged(self) -> bool:
        if len(self.turns) != 3:
            return False
        return all(t.answer.agreed is True for t in self.turns)


@dataclass
class CouncilPack:
    name: str
    shared_context: str | None
    personas: dict[ElderId, str]


@dataclass
class Debate:
    id: str
    prompt: str
    pack: CouncilPack
    rounds: list[Round]
    status: DebateStatus
    synthesis: ElderAnswer | None
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/unit/test_models.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add council/domain/models.py tests/unit/test_models.py
git commit -m "feat(domain): add core models (Debate, Round, Turn, ElderAnswer, ElderError, CouncilPack)"
```

---

## Task 3: Domain events

**Files:**
- Create: `council/domain/events.py`
- Test: `tests/unit/test_events.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_events.py`:

```python
from datetime import datetime, timezone
from council.domain.events import (
    DebateAbandoned,
    DebateEvent,
    RoundCompleted,
    SynthesisCompleted,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
)
from council.domain.models import ElderAnswer, ElderError, Round


def test_turn_started_is_debate_event():
    e: DebateEvent = TurnStarted(elder="claude", round_number=1)
    assert e.elder == "claude"
    assert e.round_number == 1


def test_turn_completed_carries_answer():
    ans = ElderAnswer(
        elder="claude",
        text="hi",
        error=None,
        agreed=True,
        created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )
    e = TurnCompleted(elder="claude", round_number=1, answer=ans)
    assert e.answer is ans


def test_turn_failed_carries_error():
    err = ElderError(elder="claude", kind="timeout", detail="")
    e = TurnFailed(elder="claude", round_number=1, error=err)
    assert e.error is err


def test_round_completed_carries_round():
    r = Round(number=1, turns=[])
    e = RoundCompleted(round=r)
    assert e.round is r


def test_synthesis_and_abandoned_shapes():
    ans = ElderAnswer(
        elder="claude",
        text="final",
        error=None,
        agreed=None,
        created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )
    assert SynthesisCompleted(answer=ans).answer is ans
    assert DebateAbandoned().__class__.__name__ == "DebateAbandoned"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/unit/test_events.py -v
```

Expected: ModuleNotFoundError on `council.domain.events`.

- [ ] **Step 3: Implement `council/domain/events.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from council.domain.models import ElderAnswer, ElderError, ElderId, Round


@dataclass(frozen=True)
class TurnStarted:
    elder: ElderId
    round_number: int


@dataclass(frozen=True)
class TurnCompleted:
    elder: ElderId
    round_number: int
    answer: ElderAnswer


@dataclass(frozen=True)
class TurnFailed:
    elder: ElderId
    round_number: int
    error: ElderError


@dataclass(frozen=True)
class RoundCompleted:
    round: Round


@dataclass(frozen=True)
class SynthesisCompleted:
    answer: ElderAnswer


@dataclass(frozen=True)
class DebateAbandoned:
    pass


DebateEvent = Union[
    TurnStarted,
    TurnCompleted,
    TurnFailed,
    RoundCompleted,
    SynthesisCompleted,
    DebateAbandoned,
]
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/unit/test_events.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add council/domain/events.py tests/unit/test_events.py
git commit -m "feat(domain): add DebateEvent union"
```

---

## Task 4: Domain ports

**Files:**
- Create: `council/domain/ports.py`

- [ ] **Step 1: Implement `council/domain/ports.py`**

Ports are Protocols — they don't need their own unit tests because they have no behavior. They'll be exercised by the contract-test suite in Task 7 and later.

```python
from __future__ import annotations

from datetime import datetime
from typing import AsyncIterator, Protocol

from council.domain.events import DebateEvent
from council.domain.models import CouncilPack, Debate, ElderId


class ElderPort(Protocol):
    elder_id: ElderId

    async def ask(self, prompt: str, *, timeout_s: float = 120.0) -> str: ...

    async def health_check(self) -> bool: ...


class TranscriptStore(Protocol):
    def save(self, debate: Debate) -> None: ...

    def load(self, debate_id: str) -> Debate: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class CouncilPackLoader(Protocol):
    def load(self, pack_name_or_path: str) -> CouncilPack: ...


class EventBus(Protocol):
    async def publish(self, event: DebateEvent) -> None: ...

    def subscribe(self) -> AsyncIterator[DebateEvent]: ...
```

- [ ] **Step 2: Verify it imports**

```bash
python -c "from council.domain.ports import ElderPort, TranscriptStore, Clock, CouncilPackLoader, EventBus; print('ok')"
```

Expected output: `ok`.

- [ ] **Step 3: Commit**

```bash
git add council/domain/ports.py
git commit -m "feat(domain): add ports (ElderPort, TranscriptStore, Clock, CouncilPackLoader, EventBus)"
```

---

## Task 5: ConvergencePolicy

**Files:**
- Create: `council/domain/convergence.py`
- Test: `tests/unit/test_convergence.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_convergence.py`:

```python
import pytest
from council.domain.convergence import ConvergencePolicy


@pytest.fixture
def policy():
    return ConvergencePolicy()


def test_parses_converged_yes(policy):
    text = "This is my answer.\n\nCONVERGED: yes"
    cleaned, agreed = policy.parse(text)
    assert cleaned == "This is my answer."
    assert agreed is True


def test_parses_converged_no(policy):
    text = "Here's my take.\nCONVERGED: no"
    cleaned, agreed = policy.parse(text)
    assert cleaned == "Here's my take."
    assert agreed is False


def test_missing_tag_returns_none(policy):
    text = "Forgot the tag."
    cleaned, agreed = policy.parse(text)
    assert cleaned == "Forgot the tag."
    assert agreed is None


def test_case_insensitive_and_whitespace_tolerant(policy):
    text = "answer\n  converged:   YES  "
    cleaned, agreed = policy.parse(text)
    assert cleaned == "answer"
    assert agreed is True


def test_only_strips_when_tag_is_last_nonblank_line(policy):
    text = "CONVERGED: yes is a weird way to start\nreal answer here"
    cleaned, agreed = policy.parse(text)
    # tag in the middle does not count
    assert agreed is None
    assert cleaned == text


def test_empty_input(policy):
    cleaned, agreed = policy.parse("")
    assert cleaned == ""
    assert agreed is None
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/unit/test_convergence.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `council/domain/convergence.py`**

```python
from __future__ import annotations

import re


class ConvergencePolicy:
    _TAG_RE = re.compile(r"^\s*converged\s*:\s*(yes|no)\s*$", re.IGNORECASE)

    def parse(self, raw: str) -> tuple[str, bool | None]:
        if not raw:
            return "", None
        lines = raw.splitlines()
        # find the last non-blank line
        last_idx = None
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip():
                last_idx = i
                break
        if last_idx is None:
            return raw, None
        m = self._TAG_RE.match(lines[last_idx])
        if not m:
            return raw, None
        agreed = m.group(1).lower() == "yes"
        cleaned = "\n".join(lines[:last_idx]).rstrip()
        return cleaned, agreed
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/unit/test_convergence.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add council/domain/convergence.py tests/unit/test_convergence.py
git commit -m "feat(domain): add ConvergencePolicy for parsing CONVERGED tag"
```

---

## Task 6: PromptBuilder

**Files:**
- Create: `council/domain/prompting.py`
- Test: `tests/unit/test_prompting.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_prompting.py`:

```python
from datetime import datetime, timezone
import pytest
from council.domain.models import CouncilPack, Debate, ElderAnswer, Round, Turn
from council.domain.prompting import PromptBuilder


def _answer(elder, text, agreed=True):
    return ElderAnswer(
        elder=elder,
        text=text,
        error=None,
        agreed=agreed,
        created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )


def _debate(prompt="What should I do?", pack=None, rounds=None):
    return Debate(
        id="abc",
        prompt=prompt,
        pack=pack or CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=rounds or [],
        status="in_progress",
        synthesis=None,
    )


@pytest.fixture
def builder():
    return PromptBuilder()


class TestRoundOne:
    def test_includes_question(self, builder):
        prompt = builder.build(_debate(), "claude", 1)
        assert "What should I do?" in prompt

    def test_requests_converged_tag(self, builder):
        prompt = builder.build(_debate(), "claude", 1)
        assert "CONVERGED: yes" in prompt
        assert "CONVERGED: no" in prompt

    def test_includes_shared_context_when_set(self, builder):
        pack = CouncilPack(name="p", shared_context="You are my chief of staff.", personas={})
        prompt = builder.build(_debate(pack=pack), "claude", 1)
        assert "You are my chief of staff." in prompt

    def test_includes_per_elder_persona_when_set(self, builder):
        pack = CouncilPack(
            name="p",
            shared_context=None,
            personas={"claude": "You are a legal advisor.", "gemini": "You are an engineer."},
        )
        claude_prompt = builder.build(_debate(pack=pack), "claude", 1)
        gemini_prompt = builder.build(_debate(pack=pack), "gemini", 1)
        assert "legal advisor" in claude_prompt
        assert "engineer" not in claude_prompt
        assert "engineer" in gemini_prompt

    def test_no_other_advisors_section_in_round_one(self, builder):
        prompt = builder.build(_debate(), "claude", 1)
        assert "Other advisors" not in prompt


class TestRoundTwoPlus:
    def test_includes_own_previous_answer(self, builder):
        prev = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_answer("claude", "My round-1 take")),
                Turn(elder="gemini", answer=_answer("gemini", "Gemini round-1")),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "ChatGPT round-1")),
            ],
        )
        prompt = builder.build(_debate(rounds=[prev]), "claude", 2)
        assert "My round-1 take" in prompt
        assert "Your previous answer" in prompt

    def test_includes_other_advisors_answers(self, builder):
        prev = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_answer("claude", "ClaudeText")),
                Turn(elder="gemini", answer=_answer("gemini", "GeminiText")),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "ChatGPTText")),
            ],
        )
        prompt = builder.build(_debate(rounds=[prev]), "claude", 2)
        assert "GeminiText" in prompt
        assert "ChatGPTText" in prompt
        assert "Other advisors" in prompt

    def test_excludes_failed_elders_from_other_advisors(self, builder):
        from council.domain.models import ElderError
        err = ElderError(elder="gemini", kind="timeout", detail="")
        failed = ElderAnswer(
            elder="gemini",
            text=None,
            error=err,
            agreed=None,
            created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        )
        prev = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_answer("claude", "ClaudeText")),
                Turn(elder="gemini", answer=failed),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "ChatGPTText")),
            ],
        )
        prompt = builder.build(_debate(rounds=[prev]), "claude", 2)
        assert "ChatGPTText" in prompt
        # the failed elder should not appear with empty content
        assert "[Gemini] \n" not in prompt


class TestSynthesis:
    def test_includes_all_rounds_and_prompt(self, builder):
        r1 = Round(
            number=1,
            turns=[
                Turn(elder="claude", answer=_answer("claude", "R1Claude")),
                Turn(elder="gemini", answer=_answer("gemini", "R1Gemini")),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "R1ChatGPT")),
            ],
        )
        r2 = Round(
            number=2,
            turns=[
                Turn(elder="claude", answer=_answer("claude", "R2Claude")),
                Turn(elder="gemini", answer=_answer("gemini", "R2Gemini")),
                Turn(elder="chatgpt", answer=_answer("chatgpt", "R2ChatGPT")),
            ],
        )
        prompt = builder.build_synthesis(_debate(rounds=[r1, r2]), by="claude")
        assert "What should I do?" in prompt
        for t in ("R1Claude", "R1Gemini", "R1ChatGPT", "R2Claude", "R2Gemini", "R2ChatGPT"):
            assert t in prompt

    def test_synthesis_does_not_request_converged_tag(self, builder):
        r1 = Round(number=1, turns=[])
        prompt = builder.build_synthesis(_debate(rounds=[r1]), by="claude")
        assert "CONVERGED" not in prompt
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/unit/test_prompting.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `council/domain/prompting.py`**

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
            parts.append(_CONVERGED_INSTRUCTION)
            return "\n\n".join(parts)

        # Round 2+
        own_prev = self._own_previous_answer(debate, elder, round_num)
        if own_prev is not None:
            parts.append(f"Your previous answer:\n{own_prev}")

        others = self._other_advisors_section(debate, elder, round_num)
        if others:
            parts.append(others)

        parts.append(
            "You may revise your answer if their arguments change your view, "
            "or stand by it."
        )
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
            "Produce the final synthesized answer that best represents the "
            "consensus (or, where no consensus exists, your best judgment "
            "informed by the debate). Do not include a CONVERGED tag."
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

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/unit/test_prompting.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add council/domain/prompting.py tests/unit/test_prompting.py
git commit -m "feat(domain): add PromptBuilder for rounds and synthesis"
```

---

## Task 7: Test doubles — FakeElder, InMemoryStore, FakeClock, InMemoryBus

**Files:**
- Create: `council/adapters/elders/fake.py`
- Create: `council/adapters/storage/in_memory.py`
- Create: `council/adapters/clock/fake.py`
- Create: `council/adapters/bus/in_memory.py`
- Test: `tests/unit/test_fakes.py`

These fakes are **shipped** in the package, not test-only. They are reused in integration tests, e2e tests, and demo scripts.

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_fakes.py`:

```python
from datetime import datetime, timezone
import pytest

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.storage.in_memory import InMemoryStore
from council.domain.events import TurnCompleted
from council.domain.models import CouncilPack, Debate, ElderAnswer


@pytest.fixture
def answer():
    return ElderAnswer(
        elder="claude",
        text="hi",
        error=None,
        agreed=True,
        created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )


@pytest.fixture
def debate():
    return Debate(
        id="d1",
        prompt="?",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[],
        status="in_progress",
        synthesis=None,
    )


class TestFakeElder:
    async def test_ask_returns_scripted_reply_in_order(self):
        e = FakeElder(elder_id="claude", replies=["first", "second"])
        assert await e.ask("q1") == "first"
        assert await e.ask("q2") == "second"

    async def test_ask_raises_when_out_of_replies(self):
        e = FakeElder(elder_id="claude", replies=["only"])
        await e.ask("q")
        with pytest.raises(AssertionError):
            await e.ask("q again")

    async def test_health_check_defaults_true(self):
        e = FakeElder(elder_id="claude", replies=[])
        assert await e.health_check() is True

    async def test_health_check_respects_flag(self):
        e = FakeElder(elder_id="claude", replies=[], healthy=False)
        assert await e.health_check() is False

    async def test_records_prompts(self):
        e = FakeElder(elder_id="claude", replies=["a", "b"])
        await e.ask("P1")
        await e.ask("P2")
        assert e.prompts == ["P1", "P2"]


class TestInMemoryStore:
    def test_save_and_load_round_trip(self, debate):
        s = InMemoryStore()
        s.save(debate)
        assert s.load("d1") is debate

    def test_load_missing_raises(self):
        s = InMemoryStore()
        with pytest.raises(KeyError):
            s.load("nope")


class TestFakeClock:
    def test_returns_initial_time_and_advances_on_demand(self):
        t0 = datetime(2026, 4, 18, 10, 0, tzinfo=timezone.utc)
        c = FakeClock(now=t0)
        assert c.now() == t0
        c.advance_seconds(30)
        assert (c.now() - t0).total_seconds() == 30


class TestInMemoryBus:
    async def test_publish_and_subscribe(self, answer):
        bus = InMemoryBus()
        received = []

        async def consume():
            async for ev in bus.subscribe():
                received.append(ev)
                if len(received) == 1:
                    return

        import asyncio
        task = asyncio.create_task(consume())
        await asyncio.sleep(0)  # let subscriber start
        await bus.publish(TurnCompleted(elder="claude", round_number=1, answer=answer))
        await task
        assert len(received) == 1
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/unit/test_fakes.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `council/adapters/elders/fake.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field

from council.domain.models import ElderId


@dataclass
class FakeElder:
    elder_id: ElderId
    replies: list[str]
    healthy: bool = True
    prompts: list[str] = field(default_factory=list)

    async def ask(self, prompt: str, *, timeout_s: float = 120.0) -> str:
        self.prompts.append(prompt)
        assert self.replies, f"FakeElder({self.elder_id}) has no more scripted replies"
        return self.replies.pop(0)

    async def health_check(self) -> bool:
        return self.healthy
```

- [ ] **Step 4: Implement `council/adapters/storage/in_memory.py`**

```python
from __future__ import annotations

from council.domain.models import Debate


class InMemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, Debate] = {}

    def save(self, debate: Debate) -> None:
        self._data[debate.id] = debate

    def load(self, debate_id: str) -> Debate:
        return self._data[debate_id]
```

- [ ] **Step 5: Implement `council/adapters/clock/fake.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class FakeClock:
    now_value: datetime

    def __init__(self, now: datetime) -> None:
        self.now_value = now

    def now(self) -> datetime:
        return self.now_value

    def advance_seconds(self, seconds: float) -> None:
        self.now_value = self.now_value + timedelta(seconds=seconds)
```

- [ ] **Step 6: Implement `council/adapters/bus/in_memory.py`**

```python
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from council.domain.events import DebateEvent


class InMemoryBus:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[DebateEvent] = asyncio.Queue()

    async def publish(self, event: DebateEvent) -> None:
        await self._queue.put(event)

    async def subscribe(self) -> AsyncIterator[DebateEvent]:
        while True:
            ev = await self._queue.get()
            yield ev
```

- [ ] **Step 7: Run tests — verify they pass**

```bash
pytest tests/unit/test_fakes.py -v
```

Expected: 8 passed.

- [ ] **Step 8: Commit**

```bash
git add council/adapters/ tests/unit/test_fakes.py
git commit -m "feat(adapters): add shipped test doubles (FakeElder, InMemoryStore, FakeClock, InMemoryBus)"
```

---

## Task 8: DebateService

**Files:**
- Create: `council/domain/debate_service.py`
- Create: `council/adapters/clock/system.py`
- Test: `tests/unit/test_debate_service.py`

- [ ] **Step 1: Implement `council/adapters/clock/system.py`** (needed by later tasks; trivial here)

```python
from __future__ import annotations

from datetime import datetime, timezone


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)
```

- [ ] **Step 2: Write failing tests**

Create `tests/unit/test_debate_service.py`:

```python
from datetime import datetime, timezone
import pytest

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.storage.in_memory import InMemoryStore
from council.domain.debate_service import DebateService
from council.domain.models import CouncilPack, Debate


def _fresh_debate():
    return Debate(
        id="d1",
        prompt="What should I do?",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[],
        status="in_progress",
        synthesis=None,
    )


@pytest.fixture
def clock():
    return FakeClock(now=datetime(2026, 4, 18, tzinfo=timezone.utc))


@pytest.fixture
def svc(clock):
    elders = {
        "claude": FakeElder(elder_id="claude", replies=["Claude round-1\nCONVERGED: yes"]),
        "gemini": FakeElder(elder_id="gemini", replies=["Gemini round-1\nCONVERGED: no"]),
        "chatgpt": FakeElder(elder_id="chatgpt", replies=["ChatGPT round-1\nCONVERGED: yes"]),
    }
    return DebateService(
        elders=elders,
        store=InMemoryStore(),
        clock=clock,
        bus=InMemoryBus(),
    ), elders


class TestRunRound:
    async def test_produces_round_with_three_turns(self, svc):
        s, _ = svc
        d = _fresh_debate()
        r = await s.run_round(d)
        assert r.number == 1
        assert {t.elder for t in r.turns} == {"claude", "gemini", "chatgpt"}

    async def test_strips_converged_tag_from_answers(self, svc):
        s, _ = svc
        d = _fresh_debate()
        r = await s.run_round(d)
        claude_turn = next(t for t in r.turns if t.elder == "claude")
        assert "CONVERGED" not in (claude_turn.answer.text or "")
        assert claude_turn.answer.agreed is True

    async def test_records_agreement_status(self, svc):
        s, _ = svc
        d = _fresh_debate()
        r = await s.run_round(d)
        by_elder = {t.elder: t.answer.agreed for t in r.turns}
        assert by_elder["claude"] is True
        assert by_elder["gemini"] is False
        assert by_elder["chatgpt"] is True

    async def test_appends_round_to_debate(self, svc):
        s, _ = svc
        d = _fresh_debate()
        await s.run_round(d)
        assert len(d.rounds) == 1

    async def test_runs_multiple_rounds(self, clock):
        elders = {
            "claude": FakeElder(
                elder_id="claude",
                replies=[
                    "R1 Claude\nCONVERGED: no",
                    "R2 Claude\nCONVERGED: yes",
                ],
            ),
            "gemini": FakeElder(
                elder_id="gemini",
                replies=[
                    "R1 Gemini\nCONVERGED: no",
                    "R2 Gemini\nCONVERGED: yes",
                ],
            ),
            "chatgpt": FakeElder(
                elder_id="chatgpt",
                replies=[
                    "R1 ChatGPT\nCONVERGED: no",
                    "R2 ChatGPT\nCONVERGED: yes",
                ],
            ),
        }
        s = DebateService(
            elders=elders, store=InMemoryStore(), clock=clock, bus=InMemoryBus()
        )
        d = _fresh_debate()
        r1 = await s.run_round(d)
        r2 = await s.run_round(d)
        assert r1.number == 1
        assert r2.number == 2
        assert d.rounds[1].converged() is True


class TestRunRoundWithFailures:
    async def test_timeout_becomes_error_turn(self, clock):
        class TimeoutElder:
            elder_id = "gemini"

            async def ask(self, prompt, *, timeout_s=120.0):
                import asyncio
                raise asyncio.TimeoutError()

            async def health_check(self):
                return True

        elders = {
            "claude": FakeElder(elder_id="claude", replies=["ok\nCONVERGED: yes"]),
            "gemini": TimeoutElder(),
            "chatgpt": FakeElder(elder_id="chatgpt", replies=["ok\nCONVERGED: yes"]),
        }
        s = DebateService(
            elders=elders, store=InMemoryStore(), clock=clock, bus=InMemoryBus()
        )
        d = _fresh_debate()
        r = await s.run_round(d)
        gem = next(t for t in r.turns if t.elder == "gemini")
        assert gem.answer.text is None
        assert gem.answer.error is not None
        assert gem.answer.error.kind == "timeout"

    async def test_any_exception_becomes_nonzero_exit_error(self, clock):
        class BrokenElder:
            elder_id = "claude"

            async def ask(self, prompt, *, timeout_s=120.0):
                raise RuntimeError("kaboom")

            async def health_check(self):
                return True

        elders = {
            "claude": BrokenElder(),
            "gemini": FakeElder(elder_id="gemini", replies=["ok\nCONVERGED: yes"]),
            "chatgpt": FakeElder(elder_id="chatgpt", replies=["ok\nCONVERGED: yes"]),
        }
        s = DebateService(
            elders=elders, store=InMemoryStore(), clock=clock, bus=InMemoryBus()
        )
        d = _fresh_debate()
        r = await s.run_round(d)
        c = next(t for t in r.turns if t.elder == "claude")
        assert c.answer.error is not None
        assert c.answer.error.kind == "nonzero_exit"
        assert "kaboom" in c.answer.error.detail


class TestSynthesize:
    async def test_produces_synthesis_answer(self, svc):
        s, _ = svc
        d = _fresh_debate()
        await s.run_round(d)
        # Prepare a synthesizer elder with a scripted synthesis reply
        s.elders["claude"].replies.append("Final synthesized answer.")
        ans = await s.synthesize(d, by="claude")
        assert ans.text == "Final synthesized answer."
        assert ans.elder == "claude"
        assert ans.error is None

    async def test_persists_debate_after_round(self, clock):
        store = InMemoryStore()
        elders = {
            "claude": FakeElder(elder_id="claude", replies=["a\nCONVERGED: yes"]),
            "gemini": FakeElder(elder_id="gemini", replies=["b\nCONVERGED: yes"]),
            "chatgpt": FakeElder(elder_id="chatgpt", replies=["c\nCONVERGED: yes"]),
        }
        s = DebateService(elders=elders, store=store, clock=clock, bus=InMemoryBus())
        d = _fresh_debate()
        await s.run_round(d)
        assert store.load("d1") is d
```

- [ ] **Step 3: Run tests — verify they fail**

```bash
pytest tests/unit/test_debate_service.py -v
```

Expected: ModuleNotFoundError on `council.domain.debate_service`.

- [ ] **Step 4: Implement `council/domain/debate_service.py`**

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from council.domain.convergence import ConvergencePolicy
from council.domain.events import (
    RoundCompleted,
    SynthesisCompleted,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
)
from council.domain.models import (
    Debate,
    ElderAnswer,
    ElderError,
    ElderId,
    Round,
    Turn,
)
from council.domain.ports import Clock, ElderPort, EventBus, TranscriptStore
from council.domain.prompting import PromptBuilder


@dataclass
class DebateService:
    elders: dict[ElderId, ElderPort]
    store: TranscriptStore
    clock: Clock
    bus: EventBus
    prompt_builder: PromptBuilder = PromptBuilder()
    convergence: ConvergencePolicy = ConvergencePolicy()

    async def run_round(self, debate: Debate) -> Round:
        round_num = len(debate.rounds) + 1

        async def _ask(elder_id: ElderId) -> Turn:
            port = self.elders[elder_id]
            prompt = self.prompt_builder.build(debate, elder_id, round_num)
            await self.bus.publish(TurnStarted(elder=elder_id, round_number=round_num))
            try:
                raw = await port.ask(prompt)
            except asyncio.TimeoutError:
                err = ElderError(elder=elder_id, kind="timeout", detail="")
                ans = self._error_answer(elder_id, err)
                await self.bus.publish(
                    TurnFailed(elder=elder_id, round_number=round_num, error=err)
                )
                return Turn(elder=elder_id, answer=ans)
            except Exception as ex:  # adapter / subprocess / misc
                err = ElderError(
                    elder=elder_id, kind="nonzero_exit", detail=repr(ex)
                )
                ans = self._error_answer(elder_id, err)
                await self.bus.publish(
                    TurnFailed(elder=elder_id, round_number=round_num, error=err)
                )
                return Turn(elder=elder_id, answer=ans)

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

        turns = await asyncio.gather(*(_ask(eid) for eid in self.elders.keys()))
        r = Round(number=round_num, turns=list(turns))
        debate.rounds.append(r)
        self.store.save(debate)
        await self.bus.publish(RoundCompleted(round=r))
        return r

    async def synthesize(self, debate: Debate, by: ElderId) -> ElderAnswer:
        port = self.elders[by]
        prompt = self.prompt_builder.build_synthesis(debate, by=by)
        try:
            raw = await port.ask(prompt)
            ans = ElderAnswer(
                elder=by,
                text=raw.strip(),
                error=None,
                agreed=None,
                created_at=self.clock.now(),
            )
        except Exception as ex:
            err = ElderError(elder=by, kind="nonzero_exit", detail=repr(ex))
            ans = self._error_answer(by, err)
        debate.synthesis = ans
        debate.status = "synthesized"
        self.store.save(debate)
        await self.bus.publish(SynthesisCompleted(answer=ans))
        return ans

    def _error_answer(self, elder_id: ElderId, err: ElderError) -> ElderAnswer:
        return ElderAnswer(
            elder=elder_id,
            text=None,
            error=err,
            agreed=None,
            created_at=self.clock.now(),
        )
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
pytest tests/unit/test_debate_service.py -v
```

Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add council/domain/debate_service.py council/adapters/clock/system.py tests/unit/test_debate_service.py
git commit -m "feat(domain): add DebateService orchestrating rounds and synthesis"
```

---

## Task 9: FilesystemPackLoader

**Files:**
- Create: `council/adapters/packs/filesystem.py`
- Test: `tests/unit/test_pack_loader.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_pack_loader.py`:

```python
from pathlib import Path
import pytest

from council.adapters.packs.filesystem import FilesystemPackLoader


@pytest.fixture
def packs_root(tmp_path: Path) -> Path:
    root = tmp_path / "packs"
    root.mkdir()
    return root


def test_loads_empty_pack(packs_root: Path):
    pack_dir = packs_root / "bare"
    pack_dir.mkdir()
    loader = FilesystemPackLoader(root=packs_root)
    pack = loader.load("bare")
    assert pack.name == "bare"
    assert pack.shared_context is None
    assert pack.personas == {}


def test_loads_shared_context(packs_root: Path):
    pack_dir = packs_root / "coo"
    pack_dir.mkdir()
    (pack_dir / "shared.md").write_text("You are my chief of staff.\n")
    loader = FilesystemPackLoader(root=packs_root)
    pack = loader.load("coo")
    assert pack.shared_context == "You are my chief of staff."


def test_loads_per_elder_personas(packs_root: Path):
    pack_dir = packs_root / "exec"
    pack_dir.mkdir()
    (pack_dir / "claude.md").write_text("Legal advisor.")
    (pack_dir / "gemini.md").write_text("Engineer.")
    (pack_dir / "chatgpt.md").write_text("Marketer.")
    loader = FilesystemPackLoader(root=packs_root)
    pack = loader.load("exec")
    assert pack.personas == {
        "claude": "Legal advisor.",
        "gemini": "Engineer.",
        "chatgpt": "Marketer.",
    }


def test_ignores_unknown_files(packs_root: Path):
    pack_dir = packs_root / "mixed"
    pack_dir.mkdir()
    (pack_dir / "shared.md").write_text("shared")
    (pack_dir / "random.txt").write_text("ignored")
    (pack_dir / "notes.md").write_text("also ignored")
    loader = FilesystemPackLoader(root=packs_root)
    pack = loader.load("mixed")
    assert pack.shared_context == "shared"
    assert pack.personas == {}


def test_absolute_path_overrides_root(tmp_path: Path, packs_root: Path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "shared.md").write_text("custom")
    loader = FilesystemPackLoader(root=packs_root)
    pack = loader.load(str(elsewhere))
    assert pack.shared_context == "custom"
    assert pack.name == "elsewhere"


def test_missing_pack_raises(packs_root: Path):
    loader = FilesystemPackLoader(root=packs_root)
    with pytest.raises(FileNotFoundError):
        loader.load("nope")
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/unit/test_pack_loader.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `council/adapters/packs/filesystem.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from council.domain.models import CouncilPack, ElderId

_ELDER_FILES: dict[str, ElderId] = {
    "claude.md": "claude",
    "gemini.md": "gemini",
    "chatgpt.md": "chatgpt",
}


@dataclass
class FilesystemPackLoader:
    root: Path

    def load(self, pack_name_or_path: str) -> CouncilPack:
        p = Path(pack_name_or_path)
        if p.is_absolute() or p.exists():
            pack_dir = p
            name = pack_dir.name
        else:
            pack_dir = self.root / pack_name_or_path
            name = pack_name_or_path
        if not pack_dir.is_dir():
            raise FileNotFoundError(f"Council pack not found: {pack_dir}")

        shared_path = pack_dir / "shared.md"
        shared = (
            shared_path.read_text(encoding="utf-8").strip()
            if shared_path.is_file()
            else None
        )
        personas: dict[ElderId, str] = {}
        for filename, elder in _ELDER_FILES.items():
            f = pack_dir / filename
            if f.is_file():
                personas[elder] = f.read_text(encoding="utf-8").strip()

        return CouncilPack(name=name, shared_context=shared, personas=personas)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/unit/test_pack_loader.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add council/adapters/packs/filesystem.py tests/unit/test_pack_loader.py
git commit -m "feat(adapters): add FilesystemPackLoader"
```

---

## Task 10: JsonFileStore

**Files:**
- Create: `council/adapters/storage/json_file.py`
- Test: `tests/unit/test_json_file_store.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_json_file_store.py`:

```python
from datetime import datetime, timezone
from pathlib import Path
import pytest

from council.adapters.storage.json_file import JsonFileStore
from council.domain.models import (
    CouncilPack,
    Debate,
    ElderAnswer,
    ElderError,
    Round,
    Turn,
)


def _round_with_all_elders() -> Round:
    t = datetime(2026, 4, 18, tzinfo=timezone.utc)
    return Round(
        number=1,
        turns=[
            Turn(
                elder="claude",
                answer=ElderAnswer(
                    elder="claude", text="ok", error=None, agreed=True, created_at=t
                ),
            ),
            Turn(
                elder="gemini",
                answer=ElderAnswer(
                    elder="gemini",
                    text=None,
                    error=ElderError(elder="gemini", kind="timeout", detail=""),
                    agreed=None,
                    created_at=t,
                ),
            ),
            Turn(
                elder="chatgpt",
                answer=ElderAnswer(
                    elder="chatgpt",
                    text="maybe",
                    error=None,
                    agreed=False,
                    created_at=t,
                ),
            ),
        ],
    )


def _debate() -> Debate:
    return Debate(
        id="d1",
        prompt="What should I do?",
        pack=CouncilPack(
            name="coo", shared_context="help", personas={"claude": "legal"}
        ),
        rounds=[_round_with_all_elders()],
        status="in_progress",
        synthesis=None,
    )


def test_save_then_load_round_trips(tmp_path: Path):
    store = JsonFileStore(root=tmp_path)
    original = _debate()
    store.save(original)
    loaded = store.load("d1")
    assert loaded.id == "d1"
    assert loaded.prompt == original.prompt
    assert loaded.pack.shared_context == "help"
    assert loaded.pack.personas == {"claude": "legal"}
    assert len(loaded.rounds) == 1
    assert {t.elder for t in loaded.rounds[0].turns} == {"claude", "gemini", "chatgpt"}
    gem = next(t for t in loaded.rounds[0].turns if t.elder == "gemini")
    assert gem.answer.error is not None
    assert gem.answer.error.kind == "timeout"


def test_load_missing_raises(tmp_path: Path):
    store = JsonFileStore(root=tmp_path)
    with pytest.raises(FileNotFoundError):
        store.load("nope")


def test_save_overwrites_existing(tmp_path: Path):
    store = JsonFileStore(root=tmp_path)
    original = _debate()
    store.save(original)
    original.status = "abandoned"
    store.save(original)
    loaded = store.load("d1")
    assert loaded.status == "abandoned"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/unit/test_json_file_store.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `council/adapters/storage/json_file.py`**

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from council.domain.models import (
    CouncilPack,
    Debate,
    ElderAnswer,
    ElderError,
    ElderId,
    Round,
    Turn,
)


@dataclass
class JsonFileStore:
    root: Path

    def save(self, debate: Debate) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{debate.id}.json"
        path.write_text(
            json.dumps(_serialize_debate(debate), indent=2), encoding="utf-8"
        )

    def load(self, debate_id: str) -> Debate:
        path = self.root / f"{debate_id}.json"
        if not path.is_file():
            raise FileNotFoundError(f"No debate with id {debate_id} at {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return _deserialize_debate(data)


def _serialize_debate(d: Debate) -> dict[str, Any]:
    return {
        "id": d.id,
        "prompt": d.prompt,
        "pack": _serialize_pack(d.pack),
        "rounds": [_serialize_round(r) for r in d.rounds],
        "status": d.status,
        "synthesis": _serialize_answer(d.synthesis) if d.synthesis else None,
    }


def _serialize_pack(p: CouncilPack) -> dict[str, Any]:
    return {
        "name": p.name,
        "shared_context": p.shared_context,
        "personas": dict(p.personas),
    }


def _serialize_round(r: Round) -> dict[str, Any]:
    return {
        "number": r.number,
        "turns": [
            {"elder": t.elder, "answer": _serialize_answer(t.answer)} for t in r.turns
        ],
    }


def _serialize_answer(a: ElderAnswer) -> dict[str, Any]:
    return {
        "elder": a.elder,
        "text": a.text,
        "error": (
            None
            if a.error is None
            else {"elder": a.error.elder, "kind": a.error.kind, "detail": a.error.detail}
        ),
        "agreed": a.agreed,
        "created_at": a.created_at.isoformat(),
    }


def _deserialize_debate(d: dict[str, Any]) -> Debate:
    return Debate(
        id=d["id"],
        prompt=d["prompt"],
        pack=_deserialize_pack(d["pack"]),
        rounds=[_deserialize_round(r) for r in d["rounds"]],
        status=d["status"],
        synthesis=_deserialize_answer(d["synthesis"]) if d["synthesis"] else None,
    )


def _deserialize_pack(p: dict[str, Any]) -> CouncilPack:
    return CouncilPack(
        name=p["name"],
        shared_context=p["shared_context"],
        personas={k: v for k, v in p["personas"].items()},
    )


def _deserialize_round(r: dict[str, Any]) -> Round:
    return Round(
        number=r["number"],
        turns=[
            Turn(elder=t["elder"], answer=_deserialize_answer(t["answer"]))
            for t in r["turns"]
        ],
    )


def _deserialize_answer(a: dict[str, Any]) -> ElderAnswer:
    err = a["error"]
    return ElderAnswer(
        elder=a["elder"],
        text=a["text"],
        error=(
            None
            if err is None
            else ElderError(elder=err["elder"], kind=err["kind"], detail=err["detail"])
        ),
        agreed=a["agreed"],
        created_at=datetime.fromisoformat(a["created_at"]),
    )
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/unit/test_json_file_store.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add council/adapters/storage/json_file.py tests/unit/test_json_file_store.py
git commit -m "feat(adapters): add JsonFileStore"
```

---

## Task 11: Shared subprocess adapter base + contract test fixture

**Files:**
- Create: `council/adapters/elders/_subprocess.py`
- Create: `tests/contract/test_elder_port_contract.py`

`_subprocess.py` holds the reusable subprocess-wrangling code that all three vendor adapters share (spawn, read stdout, honor timeout, classify exit codes). Keeping it in one place means the vendor adapters are just config: binary name, flags, auth-error detection.

- [ ] **Step 1: Implement `council/adapters/elders/_subprocess.py`**

```python
from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from typing import Callable

from council.domain.models import ElderId


class ElderSubprocessError(Exception):
    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail


@dataclass
class SubprocessElder:
    """Reusable base for shelling out to a vendor CLI.

    Concrete adapters fill in `binary`, `build_args`, and
    `classify_stderr` (to distinguish auth_failed from other nonzero exits).
    """

    elder_id: ElderId
    binary: str
    build_args: Callable[[str], list[str]]
    classify_stderr: Callable[[str], str] = lambda s: "nonzero_exit"

    async def ask(self, prompt: str, *, timeout_s: float = 120.0) -> str:
        if shutil.which(self.binary) is None:
            raise ElderSubprocessError("cli_missing", self.binary)
        proc = await asyncio.create_subprocess_exec(
            self.binary,
            *self.build_args(prompt),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise
        if proc.returncode != 0:
            detail = (stderr or b"").decode(errors="replace")[-400:]
            kind = self.classify_stderr(detail)
            raise ElderSubprocessError(kind, detail)
        return (stdout or b"").decode(errors="replace")

    async def health_check(self) -> bool:
        if shutil.which(self.binary) is None:
            return False
        try:
            proc = await asyncio.create_subprocess_exec(
                self.binary,
                "--version",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            rc = await asyncio.wait_for(proc.wait(), timeout=5.0)
            return rc == 0
        except (asyncio.TimeoutError, FileNotFoundError):
            return False
```

- [ ] **Step 2: Write the reusable contract-test fixture**

Create `tests/contract/test_elder_port_contract.py`:

```python
"""Contract tests every ElderPort implementation must satisfy.

FakeElder always runs. Real-CLI adapters are parameterized with the
`integration` marker, so they only run under `pytest -m integration`
(the default pytest config uses `-m 'not integration'`).
"""
from __future__ import annotations

import pytest

from council.adapters.elders.fake import FakeElder


def _fake_elder():
    return FakeElder(
        elder_id="claude",
        replies=["The first answer.\nCONVERGED: yes"],
    )


# Real adapter factories import lazily — they're only imported when selected.
def _claude_real():
    from council.adapters.elders.claude_code import ClaudeCodeAdapter
    return ClaudeCodeAdapter()


def _gemini_real():
    from council.adapters.elders.gemini_cli import GeminiCLIAdapter
    return GeminiCLIAdapter()


def _codex_real():
    from council.adapters.elders.codex_cli import CodexCLIAdapter
    return CodexCLIAdapter()


ELDERS_UNDER_CONTRACT = [
    pytest.param(_fake_elder, id="fake"),
    pytest.param(_claude_real, id="claude-real", marks=pytest.mark.integration),
    pytest.param(_gemini_real, id="gemini-real", marks=pytest.mark.integration),
    pytest.param(_codex_real, id="codex-real", marks=pytest.mark.integration),
]


@pytest.fixture(params=ELDERS_UNDER_CONTRACT)
def elder_factory(request):
    return request.param


class TestElderPortContract:
    async def test_ask_returns_nonempty_string(self, elder_factory):
        elder = elder_factory()
        reply = await elder.ask("Say hello.", timeout_s=60)
        assert isinstance(reply, str)
        assert reply.strip()

    async def test_health_check_is_bool(self, elder_factory):
        elder = elder_factory()
        result = await elder.health_check()
        assert isinstance(result, bool)
```

- [ ] **Step 3: Run the contract suite against `FakeElder` only**

```bash
pytest tests/contract/ -v
```

Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add council/adapters/elders/_subprocess.py tests/contract/test_elder_port_contract.py
git commit -m "feat(adapters): add subprocess base + ElderPort contract test suite"
```

---

## Task 12: ClaudeCodeAdapter

**Files:**
- Create: `council/adapters/elders/claude_code.py`
- Test: `tests/integration/test_claude_code_smoke.py`

Real-CLI contract tests are already wired in Task 11 via `pytest.param(..., marks=pytest.mark.integration)`. No conftest mutation needed here — just implement the adapter and the smoke test.

- [ ] **Step 1: Implement `council/adapters/elders/claude_code.py`**

The Claude Code CLI's non-interactive mode is `claude -p "<prompt>"` (prompt passed as argv; response printed to stdout). If the user hasn't run `claude login` it exits nonzero and stderr contains something like "Not logged in" or "authentication". We treat that as `auth_failed`.

```python
from __future__ import annotations

from council.adapters.elders._subprocess import SubprocessElder


def _classify(stderr_tail: str) -> str:
    s = stderr_tail.lower()
    if "not logged in" in s or "unauthorized" in s or "authenticat" in s:
        return "auth_failed"
    return "nonzero_exit"


class ClaudeCodeAdapter(SubprocessElder):
    def __init__(self) -> None:
        super().__init__(
            elder_id="claude",
            binary="claude",
            build_args=lambda prompt: ["-p", prompt],
            classify_stderr=_classify,
        )
```

- [ ] **Step 2: Write a single smoke test**

Create `tests/integration/test_claude_code_smoke.py`:

```python
import pytest

from council.adapters.elders.claude_code import ClaudeCodeAdapter


@pytest.mark.integration
async def test_claude_code_says_hi():
    elder = ClaudeCodeAdapter()
    if not await elder.health_check():
        pytest.skip("claude CLI not installed or not authenticated")
    reply = await elder.ask("Say exactly the word 'hi' and nothing else.", timeout_s=60)
    assert reply.strip()
```

- [ ] **Step 3: Verify non-integration run still green**

```bash
pytest -v
```

Expected: all passing; integration tests skipped/deselected.

- [ ] **Step 4: Verify integration run works locally (manual — skip if claude not installed)**

```bash
pytest -m integration tests/integration/test_claude_code_smoke.py -v
```

Expected: pass if `claude` CLI is installed + authed, otherwise skipped.

- [ ] **Step 5: Commit**

```bash
git add council/adapters/elders/claude_code.py tests/integration/test_claude_code_smoke.py
git commit -m "feat(adapters): add ClaudeCodeAdapter + integration smoke test"
```

---

## Task 13: GeminiCLIAdapter

**Files:**
- Create: `council/adapters/elders/gemini_cli.py`
- Test: `tests/integration/test_gemini_cli_smoke.py`

- [ ] **Step 1: Implement `council/adapters/elders/gemini_cli.py`**

The Gemini CLI's non-interactive mode is `gemini -p "<prompt>"` on current versions. Auth errors surface with phrases like "auth" or "credentials".

```python
from __future__ import annotations

from council.adapters.elders._subprocess import SubprocessElder


def _classify(stderr_tail: str) -> str:
    s = stderr_tail.lower()
    if "credential" in s or "auth" in s or "login" in s:
        return "auth_failed"
    return "nonzero_exit"


class GeminiCLIAdapter(SubprocessElder):
    def __init__(self) -> None:
        super().__init__(
            elder_id="gemini",
            binary="gemini",
            build_args=lambda prompt: ["-p", prompt],
            classify_stderr=_classify,
        )
```

- [ ] **Step 2: Write the smoke test**

Create `tests/integration/test_gemini_cli_smoke.py`:

```python
import pytest

from council.adapters.elders.gemini_cli import GeminiCLIAdapter


@pytest.mark.integration
async def test_gemini_cli_says_hi():
    elder = GeminiCLIAdapter()
    if not await elder.health_check():
        pytest.skip("gemini CLI not installed or not authenticated")
    reply = await elder.ask("Say exactly the word 'hi' and nothing else.", timeout_s=60)
    assert reply.strip()
```

- [ ] **Step 3: Verify default run passes**

```bash
pytest -v
```

Expected: all passing; integration not collected.

- [ ] **Step 4: Commit**

```bash
git add council/adapters/elders/gemini_cli.py tests/integration/test_gemini_cli_smoke.py
git commit -m "feat(adapters): add GeminiCLIAdapter + integration smoke test"
```

---

## Task 14: CodexCLIAdapter

**Files:**
- Create: `council/adapters/elders/codex_cli.py`
- Test: `tests/integration/test_codex_cli_smoke.py`

- [ ] **Step 1: Implement `council/adapters/elders/codex_cli.py`**

The Codex CLI's non-interactive invocation is `codex exec "<prompt>"`. If authentication is missing the CLI emits a "not signed in" / "please run codex login" style message.

```python
from __future__ import annotations

from council.adapters.elders._subprocess import SubprocessElder


def _classify(stderr_tail: str) -> str:
    s = stderr_tail.lower()
    if "not signed in" in s or "login" in s or "unauthorized" in s:
        return "auth_failed"
    return "nonzero_exit"


class CodexCLIAdapter(SubprocessElder):
    def __init__(self) -> None:
        super().__init__(
            elder_id="chatgpt",
            binary="codex",
            build_args=lambda prompt: ["exec", prompt],
            classify_stderr=_classify,
        )
```

- [ ] **Step 2: Write the smoke test**

Create `tests/integration/test_codex_cli_smoke.py`:

```python
import pytest

from council.adapters.elders.codex_cli import CodexCLIAdapter


@pytest.mark.integration
async def test_codex_cli_says_hi():
    elder = CodexCLIAdapter()
    if not await elder.health_check():
        pytest.skip("codex CLI not installed or not authenticated")
    reply = await elder.ask("Say exactly the word 'hi' and nothing else.", timeout_s=60)
    assert reply.strip()
```

- [ ] **Step 3: Verify default run still passes**

```bash
pytest -v
```

Expected: all passing; integration skipped.

- [ ] **Step 4: Commit**

```bash
git add council/adapters/elders/codex_cli.py tests/integration/test_codex_cli_smoke.py
git commit -m "feat(adapters): add CodexCLIAdapter + integration smoke test"
```

---

## Task 15: SubprocessElder error mapping — translate exceptions into ElderError kinds

**Files:**
- Modify: `council/domain/debate_service.py`
- Test: `tests/unit/test_debate_service_error_mapping.py`

Right now `DebateService` maps *any* exception to `nonzero_exit`. That's correct for arbitrary bugs, but when our own adapters raise `ElderSubprocessError` we want to preserve the `kind` (so `cli_missing` and `auth_failed` surface cleanly to the user).

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_debate_service_error_mapping.py`:

```python
from datetime import datetime, timezone
import pytest

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.fake import FakeClock
from council.adapters.elders._subprocess import ElderSubprocessError
from council.adapters.elders.fake import FakeElder
from council.adapters.storage.in_memory import InMemoryStore
from council.domain.debate_service import DebateService
from council.domain.models import CouncilPack, Debate


def _debate():
    return Debate(
        id="d1",
        prompt="?",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=[],
        status="in_progress",
        synthesis=None,
    )


class CliMissingElder:
    elder_id = "gemini"

    async def ask(self, prompt, *, timeout_s=120.0):
        raise ElderSubprocessError("cli_missing", "gemini")

    async def health_check(self):
        return False


async def test_cli_missing_preserves_error_kind():
    elders = {
        "claude": FakeElder(elder_id="claude", replies=["ok\nCONVERGED: yes"]),
        "gemini": CliMissingElder(),
        "chatgpt": FakeElder(elder_id="chatgpt", replies=["ok\nCONVERGED: yes"]),
    }
    s = DebateService(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 18, tzinfo=timezone.utc)),
        bus=InMemoryBus(),
    )
    r = await s.run_round(_debate())
    gem = next(t for t in r.turns if t.elder == "gemini")
    assert gem.answer.error is not None
    assert gem.answer.error.kind == "cli_missing"
```

- [ ] **Step 2: Run — verify it fails**

```bash
pytest tests/unit/test_debate_service_error_mapping.py -v
```

Expected: fail (the test captures `kind="nonzero_exit"`, not `"cli_missing"`).

- [ ] **Step 3: Update `council/domain/debate_service.py`**

Find the inner `_ask` function and replace the broad-exception branch. The new branch inspects `ElderSubprocessError.kind`:

```python
            except asyncio.TimeoutError:
                err = ElderError(elder=elder_id, kind="timeout", detail="")
                ans = self._error_answer(elder_id, err)
                await self.bus.publish(
                    TurnFailed(elder=elder_id, round_number=round_num, error=err)
                )
                return Turn(elder=elder_id, answer=ans)
            except Exception as ex:
                kind = getattr(ex, "kind", "nonzero_exit")
                detail = getattr(ex, "detail", repr(ex))
                err = ElderError(elder=elder_id, kind=kind, detail=detail)
                ans = self._error_answer(elder_id, err)
                await self.bus.publish(
                    TurnFailed(elder=elder_id, round_number=round_num, error=err)
                )
                return Turn(elder=elder_id, answer=ans)
```

Note: `getattr(..., "kind", ...)` keeps the domain free of an import from the adapter module — it duck-types the exception shape.

- [ ] **Step 4: Run all unit tests — verify nothing broke**

```bash
pytest tests/unit/ -v
```

Expected: all passing including the new test.

- [ ] **Step 5: Commit**

```bash
git add council/domain/debate_service.py tests/unit/test_debate_service_error_mapping.py
git commit -m "feat(domain): preserve ElderError kind from structured subprocess errors"
```

---

## Task 16: Headless entrypoint

**Files:**
- Create: `council/app/headless/main.py`
- Test: `tests/e2e/test_headless_flow.py`

The headless entrypoint runs one round, prints each elder's answer, then always synthesizes with Claude. It exists for two reasons: (1) end-to-end test harness that doesn't need a TUI, and (2) a "one-shot" mode for when you don't want the TUI.

- [ ] **Step 1: Write failing e2e test**

Create `tests/e2e/test_headless_flow.py`:

```python
from datetime import datetime, timezone
from pathlib import Path
import pytest

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.storage.in_memory import InMemoryStore
from council.app.headless.main import run_headless
from council.domain.models import CouncilPack


async def test_headless_runs_one_round_and_synthesizes(capsys):
    elders = {
        "claude": FakeElder(
            elder_id="claude",
            replies=[
                "R1 Claude\nCONVERGED: yes",
                "Final synthesized answer.",
            ],
        ),
        "gemini": FakeElder(
            elder_id="gemini", replies=["R1 Gemini\nCONVERGED: yes"]
        ),
        "chatgpt": FakeElder(
            elder_id="chatgpt", replies=["R1 ChatGPT\nCONVERGED: yes"]
        ),
    }
    pack = CouncilPack(name="bare", shared_context=None, personas={})
    await run_headless(
        prompt="What should I do?",
        pack=pack,
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 18, tzinfo=timezone.utc)),
        bus=InMemoryBus(),
        synthesizer="claude",
    )
    out = capsys.readouterr().out
    assert "R1 Claude" in out
    assert "R1 Gemini" in out
    assert "R1 ChatGPT" in out
    assert "Final synthesized answer." in out
```

- [ ] **Step 2: Run — verify it fails**

```bash
pytest tests/e2e/test_headless_flow.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `council/app/headless/main.py`**

```python
from __future__ import annotations

import argparse
import asyncio
import uuid
from pathlib import Path

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.system import SystemClock
from council.adapters.elders.claude_code import ClaudeCodeAdapter
from council.adapters.elders.codex_cli import CodexCLIAdapter
from council.adapters.elders.gemini_cli import GeminiCLIAdapter
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.json_file import JsonFileStore
from council.domain.debate_service import DebateService
from council.domain.models import CouncilPack, Debate, ElderId
from council.domain.ports import Clock, ElderPort, EventBus, TranscriptStore

_LABELS: dict[ElderId, str] = {
    "claude": "Claude",
    "gemini": "Gemini",
    "chatgpt": "ChatGPT",
}


async def run_headless(
    prompt: str,
    pack: CouncilPack,
    elders: dict[ElderId, ElderPort],
    store: TranscriptStore,
    clock: Clock,
    bus: EventBus,
    synthesizer: ElderId,
) -> None:
    debate = Debate(
        id=str(uuid.uuid4()),
        prompt=prompt,
        pack=pack,
        rounds=[],
        status="in_progress",
        synthesis=None,
    )
    svc = DebateService(elders=elders, store=store, clock=clock, bus=bus)
    r = await svc.run_round(debate)
    for t in r.turns:
        label = _LABELS[t.elder]
        if t.answer.error:
            print(f"[{label}] ERROR {t.answer.error.kind}: {t.answer.error.detail}\n")
        else:
            print(f"[{label}] {t.answer.text}\n")
    synth = await svc.synthesize(debate, by=synthesizer)
    print(f"[Synthesis by {_LABELS[synthesizer]}] {synth.text}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="council-headless")
    parser.add_argument("prompt")
    parser.add_argument("--pack", default="bare")
    parser.add_argument("--packs-root", default=str(Path.home() / ".council" / "packs"))
    parser.add_argument(
        "--synthesizer", choices=["claude", "gemini", "chatgpt"], default="claude"
    )
    parser.add_argument(
        "--store-root", default=str(Path.home() / ".council" / "debates")
    )
    args = parser.parse_args()

    packs_root = Path(args.packs_root)
    packs_root.mkdir(parents=True, exist_ok=True)
    pack = FilesystemPackLoader(root=packs_root).load(args.pack) if (
        packs_root / args.pack
    ).is_dir() else CouncilPack(name=args.pack, shared_context=None, personas={})

    elders: dict[ElderId, ElderPort] = {
        "claude": ClaudeCodeAdapter(),
        "gemini": GeminiCLIAdapter(),
        "chatgpt": CodexCLIAdapter(),
    }
    asyncio.run(
        run_headless(
            prompt=args.prompt,
            pack=pack,
            elders=elders,
            store=JsonFileStore(root=Path(args.store_root)),
            clock=SystemClock(),
            bus=InMemoryBus(),
            synthesizer=args.synthesizer,
        )
    )
```

- [ ] **Step 4: Run — verify it passes**

```bash
pytest tests/e2e/test_headless_flow.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add council/app/headless/main.py tests/e2e/test_headless_flow.py
git commit -m "feat(app): add headless entrypoint (used for e2e harness + one-shot mode)"
```

---

## Task 17: Textual TUI — chronological stream widget

**Files:**
- Create: `council/app/tui/stream.py`
- Test: `tests/unit/test_stream_widget.py`

The `ChronologicalStream` widget is a `RichLog`-backed scrolling view that accepts `DebateEvent`s and renders each one as a colored, labeled line.

- [ ] **Step 1: Write failing test (does not require a running app)**

Create `tests/unit/test_stream_widget.py`:

```python
from datetime import datetime, timezone
import pytest

from council.app.tui.stream import format_event
from council.domain.events import (
    RoundCompleted,
    SynthesisCompleted,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
)
from council.domain.models import ElderAnswer, ElderError, Round


def _answer(elder="claude", text="hi"):
    return ElderAnswer(
        elder=elder,
        text=text,
        error=None,
        agreed=True,
        created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )


def test_turn_started_renders_status_line():
    s = format_event(TurnStarted(elder="claude", round_number=1))
    assert "Claude" in s
    assert "round 1" in s.lower()


def test_turn_completed_renders_with_label():
    s = format_event(TurnCompleted(elder="gemini", round_number=1, answer=_answer("gemini", "gx")))
    assert "[Gemini]" in s
    assert "gx" in s


def test_turn_failed_renders_error():
    err = ElderError(elder="chatgpt", kind="timeout", detail="")
    s = format_event(TurnFailed(elder="chatgpt", round_number=1, error=err))
    assert "ChatGPT" in s
    assert "timeout" in s.lower()


def test_round_completed_renders_divider():
    r = Round(number=2, turns=[])
    s = format_event(RoundCompleted(round=r))
    assert "Round 2 complete" in s


def test_synthesis_renders_with_label():
    s = format_event(SynthesisCompleted(answer=_answer("claude", "final")))
    assert "[Synthesis" in s
    assert "final" in s
```

- [ ] **Step 2: Run — verify it fails**

```bash
pytest tests/unit/test_stream_widget.py -v
```

Expected: ModuleNotFoundError on `council.app.tui.stream`.

- [ ] **Step 3: Implement `council/app/tui/stream.py`**

```python
from __future__ import annotations

from textual.widgets import RichLog

from council.domain.events import (
    DebateAbandoned,
    DebateEvent,
    RoundCompleted,
    SynthesisCompleted,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
)
from council.domain.models import ElderId

_LABELS: dict[ElderId, str] = {"claude": "Claude", "gemini": "Gemini", "chatgpt": "ChatGPT"}
_COLORS: dict[ElderId, str] = {"claude": "magenta", "gemini": "cyan", "chatgpt": "green"}


def format_event(event: DebateEvent) -> str:
    """Produce a Rich-markup-formatted line for an event."""
    if isinstance(event, TurnStarted):
        c = _COLORS[event.elder]
        return f"[dim][{c}]{_LABELS[event.elder]}[/] is thinking… (round {event.round_number})[/dim]"
    if isinstance(event, TurnCompleted):
        c = _COLORS[event.elder]
        tag = ""
        if event.answer.agreed is True:
            tag = " [green](converged)[/green]"
        elif event.answer.agreed is False:
            tag = " [yellow](dissenting)[/yellow]"
        return f"[bold {c}][{_LABELS[event.elder]}][/]{tag}\n{event.answer.text or ''}\n"
    if isinstance(event, TurnFailed):
        c = _COLORS[event.elder]
        return (
            f"[bold {c}][{_LABELS[event.elder]}][/] "
            f"[red]ERROR {event.error.kind}[/red]: {event.error.detail}"
        )
    if isinstance(event, RoundCompleted):
        return f"[dim]— Round {event.round.number} complete —[/dim]"
    if isinstance(event, SynthesisCompleted):
        return (
            f"[bold yellow][Synthesis by {_LABELS[event.answer.elder]}][/]\n"
            f"{event.answer.text or ''}\n"
        )
    if isinstance(event, DebateAbandoned):
        return "[dim]— Debate abandoned —[/dim]"
    return ""


class ChronologicalStream(RichLog):
    def __init__(self, **kwargs):
        super().__init__(markup=True, wrap=True, highlight=False, **kwargs)

    def write_event(self, event: DebateEvent) -> None:
        line = format_event(event)
        if line:
            self.write(line)
```

- [ ] **Step 4: Run — verify it passes**

```bash
pytest tests/unit/test_stream_widget.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add council/app/tui/stream.py tests/unit/test_stream_widget.py
git commit -m "feat(tui): add ChronologicalStream widget and event formatter"
```

---

## Task 18: Textual TUI — app shell with user control

**Files:**
- Create: `council/app/tui/app.py`
- Test: `tests/e2e/test_tui_full_debate.py`

The app has three states:

1. **Prompt entry** — an `Input` at the bottom collects the initial question.
2. **Running** — fans out to all three elders, streams events; input disabled.
3. **Between rounds** — shows a toolbar: `[C]ontinue`, `[S]ynthesize`, `[A]bandon`, `[O]verride`. User presses a key.

When `[S]` is pressed the TUI prompts for the synthesizer choice via a modal (Claude/Gemini/ChatGPT).

- [ ] **Step 1: Write the e2e test**

Create `tests/e2e/test_tui_full_debate.py`:

```python
from datetime import datetime, timezone
import pytest

from council.adapters.clock.fake import FakeClock
from council.adapters.elders.fake import FakeElder
from council.adapters.storage.in_memory import InMemoryStore
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.app.tui.app import CouncilApp


async def test_full_debate_via_tui(tmp_path):
    # Pack with only shared context
    (tmp_path / "bare").mkdir()
    loader = FilesystemPackLoader(root=tmp_path)

    elders = {
        "claude": FakeElder(
            elder_id="claude",
            replies=[
                "R1 Claude\nCONVERGED: yes",
                "Final synthesized answer.",
            ],
        ),
        "gemini": FakeElder(
            elder_id="gemini", replies=["R1 Gemini\nCONVERGED: yes"]
        ),
        "chatgpt": FakeElder(
            elder_id="chatgpt", replies=["R1 ChatGPT\nCONVERGED: yes"]
        ),
    }
    app = CouncilApp(
        elders=elders,
        store=InMemoryStore(),
        clock=FakeClock(now=datetime(2026, 4, 18, tzinfo=timezone.utc)),
        pack_loader=loader,
        pack_name="bare",
    )

    async with app.run_test() as pilot:
        await pilot.press(*"What should I do?")
        await pilot.press("enter")
        # Wait for round to complete; fake elders are instant
        for _ in range(20):
            await pilot.pause()
            if app.awaiting_decision:
                break
        assert app.awaiting_decision is True
        # Press S to synthesize
        await pilot.press("s")
        # Synthesizer modal appears; choose Claude
        await pilot.press("1")  # 1 => Claude
        for _ in range(20):
            await pilot.pause()
            if app.is_finished:
                break
        assert app.is_finished is True

    # Stream should contain all three elder answers and the synthesis
    transcript = "\n".join(app.rendered_lines)
    assert "R1 Claude" in transcript
    assert "R1 Gemini" in transcript
    assert "R1 ChatGPT" in transcript
    assert "Final synthesized answer." in transcript
```

- [ ] **Step 2: Run — verify it fails**

```bash
pytest tests/e2e/test_tui_full_debate.py -v
```

Expected: ModuleNotFoundError on `council.app.tui.app`.

- [ ] **Step 3: Implement `council/app/tui/app.py`**

```python
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Static

from council.adapters.bus.in_memory import InMemoryBus
from council.adapters.clock.system import SystemClock
from council.adapters.elders.claude_code import ClaudeCodeAdapter
from council.adapters.elders.codex_cli import CodexCLIAdapter
from council.adapters.elders.gemini_cli import GeminiCLIAdapter
from council.adapters.packs.filesystem import FilesystemPackLoader
from council.adapters.storage.json_file import JsonFileStore
from council.app.tui.stream import ChronologicalStream, format_event
from council.domain.debate_service import DebateService
from council.domain.events import (
    RoundCompleted,
    SynthesisCompleted,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
)
from council.domain.models import (
    CouncilPack,
    Debate,
    ElderId,
)
from council.domain.ports import (
    Clock,
    CouncilPackLoader,
    ElderPort,
    TranscriptStore,
)


class SynthesizerModal(ModalScreen[ElderId]):
    BINDINGS = [
        Binding("1", "pick('claude')", "Claude"),
        Binding("2", "pick('gemini')", "Gemini"),
        Binding("3", "pick('chatgpt')", "ChatGPT"),
        Binding("escape", "dismiss(None)", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("Who should synthesize?"),
            Static("[1] Claude   [2] Gemini   [3] ChatGPT   [Esc] Cancel"),
        )

    def action_pick(self, elder: str) -> None:
        self.dismiss(elder)  # type: ignore[arg-type]


class CouncilApp(App):
    CSS = """
    #stream { height: 1fr; }
    #toolbar { height: 3; dock: bottom; }
    #input { dock: bottom; }
    """
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("c", "continue_round", "Continue", show=False),
        Binding("s", "synthesize", "Synthesize", show=False),
        Binding("a", "abandon", "Abandon", show=False),
        Binding("o", "override", "Override convergence", show=False),
    ]

    def __init__(
        self,
        *,
        elders: dict[ElderId, ElderPort],
        store: TranscriptStore,
        clock: Clock,
        pack_loader: CouncilPackLoader,
        pack_name: str,
    ) -> None:
        super().__init__()
        self._elders = elders
        self._store = store
        self._clock = clock
        self._pack_loader = pack_loader
        self._pack_name = pack_name
        self._bus = InMemoryBus()
        self._service = DebateService(
            elders=elders, store=store, clock=clock, bus=self._bus
        )
        self._debate: Debate | None = None
        self.awaiting_decision: bool = False
        self.is_finished: bool = False
        self.rendered_lines: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield ChronologicalStream(id="stream")
        yield Input(placeholder="Ask the council…", id="input")
        yield Footer()

    async def on_mount(self) -> None:
        self._stream_task = asyncio.create_task(self._consume_events())

    async def _consume_events(self) -> None:
        async for ev in self._bus.subscribe():
            stream = self.query_one("#stream", ChronologicalStream)
            line = format_event(ev)
            if line:
                self.rendered_lines.append(line)
                stream.write(line)
            if isinstance(ev, RoundCompleted):
                self.awaiting_decision = True
            if isinstance(ev, SynthesisCompleted):
                self.is_finished = True
                self.awaiting_decision = False

    @on(Input.Submitted, "#input")
    async def _on_prompt_submitted(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        if not prompt or self._debate is not None:
            return
        pack = self._pack_loader.load(self._pack_name)
        self._debate = Debate(
            id=str(uuid.uuid4()),
            prompt=prompt,
            pack=pack,
            rounds=[],
            status="in_progress",
            synthesis=None,
        )
        self.query_one("#input", Input).disabled = True
        await self._service.run_round(self._debate)

    async def action_continue_round(self) -> None:
        if not self.awaiting_decision or self._debate is None:
            return
        self.awaiting_decision = False
        await self._service.run_round(self._debate)

    async def action_abandon(self) -> None:
        if self._debate is None:
            return
        self._debate.status = "abandoned"
        self.is_finished = True
        self.awaiting_decision = False
        self.exit()

    async def action_override(self) -> None:
        if not self.awaiting_decision or not self._debate or not self._debate.rounds:
            return
        # Force all turns to agreed=True for the most recent round
        from dataclasses import replace
        r = self._debate.rounds[-1]
        r.turns = [
            type(t)(elder=t.elder, answer=replace(t.answer, agreed=True))
            for t in r.turns
        ]

    async def action_synthesize(self) -> None:
        if not self.awaiting_decision or self._debate is None:
            return
        choice = await self.push_screen_wait(SynthesizerModal())
        if choice is None:
            return
        self.awaiting_decision = False
        await self._service.synthesize(self._debate, by=choice)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="council")
    parser.add_argument("--pack", default="bare")
    parser.add_argument("--packs-root", default=str(Path.home() / ".council" / "packs"))
    parser.add_argument(
        "--store-root", default=str(Path.home() / ".council" / "debates")
    )
    args = parser.parse_args()

    packs_root = Path(args.packs_root)
    packs_root.mkdir(parents=True, exist_ok=True)
    (packs_root / args.pack).mkdir(exist_ok=True)  # ensure bare pack works

    app = CouncilApp(
        elders={
            "claude": ClaudeCodeAdapter(),
            "gemini": GeminiCLIAdapter(),
            "chatgpt": CodexCLIAdapter(),
        },
        store=JsonFileStore(root=Path(args.store_root)),
        clock=SystemClock(),
        pack_loader=FilesystemPackLoader(root=packs_root),
        pack_name=args.pack,
    )
    app.run()
```

- [ ] **Step 4: Run — verify it passes**

```bash
pytest tests/e2e/test_tui_full_debate.py -v
```

Expected: 1 passed (may take a couple of seconds — Textual pilot spins up an offscreen app).

- [ ] **Step 5: Run the full test suite — everything green**

```bash
pytest -v
```

Expected: all passing; integration tests skipped.

- [ ] **Step 6: Commit**

```bash
git add council/app/tui/app.py tests/e2e/test_tui_full_debate.py
git commit -m "feat(tui): add CouncilApp with user-controlled convergence flow"
```

---

## Task 19: Polish — ruff, manual smoke, README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run linter and auto-fix**

```bash
ruff check council/ tests/ --fix
ruff format council/ tests/
```

- [ ] **Step 2: Re-run full test suite**

```bash
pytest -v
```

Expected: all passing.

- [ ] **Step 3: Flesh out `README.md`**

Overwrite `README.md` with:

```markdown
# Council of Elders

A terminal UI that sends one prompt to Claude Code, Gemini CLI, and Codex CLI concurrently, runs a user-controlled convergence-based debate, and produces a single synthesized answer — all using your existing paid subscriptions (no API charges).

## Requirements

- Python 3.12+
- Claude Code CLI (`claude`), logged in via `claude login`
- Gemini CLI (`gemini`), logged in via `gemini auth login`
- Codex CLI (`codex`), logged in via `codex login`

## Install

```bash
uv pip install -e .
```

## Use

```bash
council                          # bare pack
council --pack chief-of-staff    # load ~/.council/packs/chief-of-staff/
```

Keybindings when a round completes:

| Key | Action |
|---|---|
| `c` | Continue — run another round |
| `s` | Synthesize now — pick who writes the final answer |
| `a` | Abandon the debate |
| `o` | Override convergence — treat everyone as agreed |

## Council packs

Create `~/.council/packs/<name>/` with any of:

- `shared.md` — applied to all three elders
- `claude.md` / `gemini.md` / `chatgpt.md` — per-elder overrides

All files optional.

## Testing

```bash
pytest                        # unit + e2e (fast)
pytest -m integration         # also runs real CLIs (requires auth)
```
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: write usage README"
```

- [ ] **Step 5: Manual smoke test (optional, requires vendor CLIs)**

```bash
mkdir -p ~/.council/packs/bare
council --pack bare
```

Type a real question, confirm answers stream in, press `s`, choose a synthesizer, see the synthesis.

---

## Spec coverage audit

| Spec section | Covered by |
|---|---|
| Hexagonal architecture | Tasks 2–8 (domain core) + 7, 9, 10, 12–14, 17, 18 (adapters) |
| Domain model | Task 2 |
| Domain events | Task 3 |
| Ports | Task 4 |
| ConvergencePolicy | Task 5 |
| PromptBuilder (rounds 1, 2+, synthesis) | Task 6 |
| Test doubles shipped in package | Task 7 |
| DebateService with asyncio.gather concurrency | Task 8 |
| Council packs (filesystem loader) | Task 9 |
| JSON persistence | Task 10 |
| ElderPort contract test | Task 11 |
| ClaudeCodeAdapter | Task 12 |
| GeminiCLIAdapter | Task 13 |
| CodexCLIAdapter | Task 14 |
| Errors-as-values (timeout/cli_missing/auth_failed/nonzero_exit preserved) | Tasks 8 + 15 |
| Headless entrypoint | Task 16 |
| Chronological stream, color-coded labels | Task 17 |
| Textual TUI with user control (c/s/a/o) | Task 18 |
| Unit / contract / integration / e2e test layers | Tasks 2–10 / 11 / 12–14 / 16, 18 |
| TDD red → green → refactor per unit | Every task |
| Package layout (council/domain, adapters, app) | Task 1 |
| v1 out-of-scope items (resume, 4th elder, streaming tokens, history browser) | Not implemented, as intended |

No gaps.

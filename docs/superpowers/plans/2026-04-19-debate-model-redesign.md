# Debate Model Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flawed "any-round-convergence / optional-questions" debate model with a three-phase forced-dialogue model, and give each elder a true multi-turn conversation with memory. Keep the system open to alternative rule sets via a `DebateRules` Protocol.

**Architecture:** `DebateService` consumes a `DebateRules` Protocol; `DefaultRules` implements the three-phase model (silent R1 / forced cross-exam R2 / open R3+). Each elder gets a persistent `list[Message]` conversation. OpenRouter uses native multi-turn. CLI adapters flatten to a single tagged prompt.

**Tech Stack:** Python 3.12+, asyncio, httpx, Textual, pytest. No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-04-19-debate-model-redesign-design.md` (commit c0ff2c0).

---

## File Structure

**New files:**
- `council/domain/rules.py` — `DebateRules` Protocol, `DefaultRules` facade, `ValidationOk`/`Violation` types.
- `council/domain/validation.py` — `TurnValidator` (per-phase contract matrix).
- `council/adapters/elders/_flatten.py` — `flatten_conversation(conv) -> str` helper for CLI adapters.
- `tests/unit/test_rules.py` — `DefaultRules` facade + Protocol usage tests.
- `tests/unit/test_validation.py` — full phase contract matrix.
- `tests/unit/test_flatten_conversation.py` — role tagging, separators, system-optional.

**Modified files:**
- `council/domain/models.py` — add `Role`, `Message` NamedTuple.
- `council/domain/ports.py` — `ElderPort.ask(conversation: list[Message]) -> str`.
- `council/domain/prompting.py` — split `build()` into `build_system_message`, `build_round_1_user`, `build_round_2_user`, `build_round_n_user`, `build_retry_reminder`. Remove `build()`. Delete `_QUESTIONS_INSTRUCTION` / `_CONVERGED_INSTRUCTION` constants and `_own_previous_answer` helper.
- `council/domain/debate_service.py` — replace `prompt_builder` with `rules: DebateRules`. Add `conversations: dict[ElderId, list[Message]]`. Rewrite per-elder loop with validator retry branch + conversation growth.
- `council/adapters/elders/openrouter.py` — `ask(conversation)`; pass messages array directly.
- `council/adapters/elders/claude_code.py` / `gemini_cli.py` / `codex_cli.py` — `ask(conversation)`; flatten via helper.
- `council/app/tui/app.py` — R1+R2 auto-chain; auto-synth modal on `rules.is_converged()`.
- `council/app/headless/main.py` — R1+R2 auto; `--max-rounds` flag (default 3, reject <2).
- `tests/unit/test_prompting.py` — rewrite for new methods.
- `tests/unit/test_debate_service.py` — new retry + conversation-growth tests.
- `tests/unit/test_openrouter_adapter.py` — updated for messages-array contract.
- `tests/unit/test_claude_code_adapter.py` / `test_gemini_cli_adapter.py` / `test_codex_cli_adapter.py` — updated for flatten behaviour.
- `tests/contract/test_elder_port_contract.py` — updated port contract.
- `tests/e2e/test_tui_full_debate.py` — R1+R2 auto-chain; R3+ flow; auto-synth modal.
- `tests/e2e/test_tui_elder_questions.py` — R2-always-has-questions expectations.
- `tests/e2e/test_headless_flow.py` — R1+R2 + `--max-rounds`.
- `README.md` — rewrite "Participating in the debate" section; update `c` keybinding description.
- `docs/USAGE.md` — new "How the debate mechanic works" section.

---

## Task 1: Add `Message` NamedTuple to domain models

**Files:**
- Modify: `council/domain/models.py`
- Test: covered indirectly by later tasks; no dedicated test here (it's a trivial type).

- [ ] **Step 1: Add Role and Message to models.py**

After the existing `ElderId` type alias:

```python
Role = Literal["system", "user", "assistant"]


class Message(NamedTuple):
    role: Role
    content: str
```

Add `NamedTuple` to the `typing` import.

- [ ] **Step 2: Run existing tests to verify nothing broke**

Run: `pytest -q`
Expected: All 220 tests still pass.

- [ ] **Step 3: Commit**

```bash
git add council/domain/models.py
git commit -m "feat(domain): add Message NamedTuple for elder conversations"
```

---

## Task 2: Add `flatten_conversation` helper for CLI adapters

**Files:**
- Create: `council/adapters/elders/_flatten.py`
- Create: `tests/unit/test_flatten_conversation.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_flatten_conversation.py
from council.adapters.elders._flatten import flatten_conversation
from council.domain.models import Message


def test_user_only_single_turn():
    conv = [Message("user", "What is 2+2?")]
    out = flatten_conversation(conv)
    assert out == "USER:\nWhat is 2+2?"


def test_system_user_assistant_user():
    conv = [
        Message("system", "You are helpful."),
        Message("user", "Hi"),
        Message("assistant", "Hello!"),
        Message("user", "Explain gravity."),
    ]
    out = flatten_conversation(conv)
    expected = (
        "SYSTEM:\nYou are helpful.\n\n"
        "USER:\nHi\n\n"
        "ASSISTANT:\nHello!\n\n"
        "USER:\nExplain gravity."
    )
    assert out == expected


def test_omits_system_when_absent():
    conv = [
        Message("user", "Hi"),
        Message("assistant", "Hello!"),
        Message("user", "Bye"),
    ]
    out = flatten_conversation(conv)
    assert out.startswith("USER:\nHi")
    assert "SYSTEM:" not in out


def test_empty_raises():
    import pytest
    with pytest.raises(ValueError):
        flatten_conversation([])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_flatten_conversation.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement helper**

```python
# council/adapters/elders/_flatten.py
from __future__ import annotations

from council.domain.models import Message

_TAG = {"system": "SYSTEM", "user": "USER", "assistant": "ASSISTANT"}


def flatten_conversation(conv: list[Message]) -> str:
    if not conv:
        raise ValueError("conversation must be non-empty")
    parts = [f"{_TAG[role]}:\n{content}" for role, content in conv]
    return "\n\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_flatten_conversation.py -v`
Expected: PASS (all 4 tests).

- [ ] **Step 5: Commit**

```bash
git add council/adapters/elders/_flatten.py tests/unit/test_flatten_conversation.py
git commit -m "feat(adapters): add flatten_conversation helper for CLI adapters"
```

---

## Task 3: Update `ElderPort.ask()` signature + all 4 adapters

**Files:**
- Modify: `council/domain/ports.py`
- Modify: `council/adapters/elders/openrouter.py`
- Modify: `council/adapters/elders/claude_code.py`
- Modify: `council/adapters/elders/gemini_cli.py`
- Modify: `council/adapters/elders/codex_cli.py`
- Modify: `tests/unit/test_openrouter_adapter.py`
- Modify: `tests/unit/test_claude_code_adapter.py` (if exists) / similar for gemini / codex
- Modify: `tests/contract/test_elder_port_contract.py`
- Modify: `council/domain/debate_service.py` (temporary bridge — wrap old prompt into a single-message conversation until Task 7 rewrites this properly)

This task is larger than a single bite because the port change cascades. Keep it atomic to avoid a broken state between commits.

- [ ] **Step 1: Verify current port signature**

Run: `grep -n "def ask" council/domain/ports.py`
Expected output: current signature is `async def ask(self, prompt: str) -> str:` or similar.

- [ ] **Step 2: Update `ElderPort.ask` signature**

In `council/domain/ports.py`, change:

```python
async def ask(self, prompt: str, *, timeout_s: float = 45.0) -> str: ...
```

to:

```python
async def ask(self, conversation: list[Message], *, timeout_s: float = 45.0) -> str: ...
```

(Adjust to match the exact existing signature — check the file first. Preserve any existing `timeout_s` default.) Add `Message` to imports.

- [ ] **Step 3: Update `OpenRouterAdapter.ask`**

In `council/adapters/elders/openrouter.py`:

```python
async def ask(self, conversation: list[Message], *, timeout_s: float = 45.0) -> str:
    if not conversation:
        raise ValueError("conversation must be non-empty")
    messages = [{"role": role, "content": content} for role, content in conversation]
    body = {
        "model": self._model,
        "messages": messages,
        "usage": {"include": True},
    }
    # ...rest of existing body construction, headers, POST, response parsing unchanged.
```

Replace the previous single-`user`-message body-construction with the new `messages` list derived from `conversation`. Preserve cost accounting, error mapping, reasoning-fallback, and headers exactly as today.

- [ ] **Step 4: Update CLI adapters**

For each of `claude_code.py`, `gemini_cli.py`, `codex_cli.py`:

```python
from council.adapters.elders._flatten import flatten_conversation
from council.domain.models import Message

async def ask(self, conversation: list[Message], *, timeout_s: float = 45.0) -> str:
    prompt = flatten_conversation(conversation)
    # ... existing subprocess invocation, passing `prompt` where `prompt` used to be passed.
```

Keep all existing argv construction, env handling, error mapping, timeout wiring unchanged. The only substantive change is constructing `prompt` from the conversation at the top of the method.

- [ ] **Step 5: Update unit tests for adapters**

For each adapter test (start with `tests/unit/test_openrouter_adapter.py`):
- Update test fixtures to pass `list[Message]` to `ask()` instead of a string.
- For OpenRouter: assert the posted body contains `"messages": [...]` matching the input conversation.
- For CLI adapters: verify the spawned subprocess receives the flattened string.

Example pattern for OpenRouter success test:

```python
from council.domain.models import Message

conversation = [Message("user", "What is 2+2?")]
result = await adapter.ask(conversation)

# Inspect the captured POST body:
assert captured_body["messages"] == [{"role": "user", "content": "What is 2+2?"}]
```

For CLI adapters, the existing tests likely assert a substring of the prompt reaches the subprocess. Update the assertion to expect the flattened format.

- [ ] **Step 6: Update contract test**

In `tests/contract/test_elder_port_contract.py`, update any `.ask(some_string)` calls to `.ask([Message("user", some_string)])`.

- [ ] **Step 7: Add temporary bridge in `DebateService`**

Task 7 rewrites `DebateService.run_round` properly. Until then, keep the service compiling by wrapping the built prompt in a one-turn conversation:

In `council/domain/debate_service.py`, inside `_ask`, change:

```python
raw = await port.ask(prompt)
```

to:

```python
from council.domain.models import Message   # add to imports
raw = await port.ask([Message("user", prompt)])
```

This is throwaway; Task 7 removes it. It keeps the build green between commits.

- [ ] **Step 8: Run all tests**

Run: `pytest -q`
Expected: PASS. If anything in the subprocess / integration stubs breaks, fix it by updating the stub call sites to pass `list[Message]`.

- [ ] **Step 9: Format + lint**

Run: `ruff format council/ tests/ && ruff check council/ tests/`
Expected: All checks passed.

- [ ] **Step 10: Commit**

```bash
git add council/domain/ports.py council/domain/models.py council/adapters/ tests/
git commit -m "feat(port): ElderPort.ask takes list[Message] for multi-turn conversations"
```

---

## Task 4: Create `TurnValidator` with full phase contract matrix

**Files:**
- Create: `council/domain/validation.py`
- Create: `tests/unit/test_validation.py`

- [ ] **Step 1: Write failing tests for full matrix**

```python
# tests/unit/test_validation.py
import pytest

from council.domain.models import ElderQuestion
from council.domain.validation import TurnValidator, ValidationOk, Violation


@pytest.fixture
def validator():
    return TurnValidator()


def _q(from_elder="claude", to_elder="gemini", text="why?", round_number=2):
    return ElderQuestion(from_elder=from_elder, to_elder=to_elder, text=text, round_number=round_number)


class TestRoundOne:
    def test_ok_with_nothing_extra(self, validator):
        r = validator.validate(agreed=None, questions=(), round_num=1, from_elder="claude")
        assert isinstance(r, ValidationOk)

    def test_unexpected_convergence(self, validator):
        r = validator.validate(agreed=True, questions=(), round_num=1, from_elder="claude")
        assert isinstance(r, Violation)
        assert r.reason == "r1_unexpected_convergence"

    def test_unexpected_questions(self, validator):
        r = validator.validate(agreed=None, questions=(_q(round_number=1),), round_num=1, from_elder="claude")
        assert isinstance(r, Violation)
        assert r.reason == "r1_unexpected_questions"


class TestRoundTwo:
    def test_ok_with_one_peer_question(self, validator):
        r = validator.validate(agreed=None, questions=(_q(),), round_num=2, from_elder="claude")
        assert isinstance(r, ValidationOk)

    def test_missing_question(self, validator):
        r = validator.validate(agreed=None, questions=(), round_num=2, from_elder="claude")
        assert isinstance(r, Violation)
        assert r.reason == "r2_missing_question"

    def test_multiple_questions(self, validator):
        qs = (_q(to_elder="gemini"), _q(to_elder="chatgpt"))
        r = validator.validate(agreed=None, questions=qs, round_num=2, from_elder="claude")
        assert isinstance(r, Violation)
        assert r.reason == "r2_multiple_questions"

    def test_unexpected_convergence(self, validator):
        r = validator.validate(agreed=True, questions=(_q(),), round_num=2, from_elder="claude")
        assert isinstance(r, Violation)
        assert r.reason == "r2_unexpected_convergence"


class TestRoundThreePlus:
    @pytest.mark.parametrize("n", [3, 5, 12])
    def test_ok_converged_yes(self, validator, n):
        r = validator.validate(agreed=True, questions=(), round_num=n, from_elder="claude")
        assert isinstance(r, ValidationOk)

    def test_ok_converged_no_with_question(self, validator):
        r = validator.validate(agreed=False, questions=(_q(round_number=3),), round_num=3, from_elder="claude")
        assert isinstance(r, ValidationOk)

    def test_missing_convergence(self, validator):
        r = validator.validate(agreed=None, questions=(), round_num=3, from_elder="claude")
        assert isinstance(r, Violation)
        assert r.reason == "rn_missing_convergence"

    def test_no_with_missing_question(self, validator):
        r = validator.validate(agreed=False, questions=(), round_num=3, from_elder="claude")
        assert isinstance(r, Violation)
        assert r.reason == "rn_no_converged_missing_question"

    def test_no_with_multiple_questions(self, validator):
        qs = (_q(to_elder="gemini", round_number=3), _q(to_elder="chatgpt", round_number=3))
        r = validator.validate(agreed=False, questions=qs, round_num=3, from_elder="claude")
        assert isinstance(r, Violation)
        assert r.reason == "rn_multiple_questions"

    def test_yes_with_question_not_a_violation(self, validator):
        # yes+question is "drop with warn" territory — validator returns OK,
        # DebateService discards the question.
        r = validator.validate(agreed=True, questions=(_q(round_number=3),), round_num=3, from_elder="claude")
        assert isinstance(r, ValidationOk)
```

- [ ] **Step 2: Run to confirm failures**

Run: `pytest tests/unit/test_validation.py -v`
Expected: all FAIL — module doesn't exist.

- [ ] **Step 3: Implement validator**

```python
# council/domain/validation.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from council.domain.models import ElderId, ElderQuestion


@dataclass(frozen=True)
class ValidationOk:
    pass


@dataclass(frozen=True)
class Violation:
    reason: str
    detail: str


ValidationResult = Union[ValidationOk, Violation]


class TurnValidator:
    def validate(
        self,
        *,
        agreed: bool | None,
        questions: tuple[ElderQuestion, ...],
        round_num: int,
        from_elder: ElderId,
    ) -> ValidationResult:
        if round_num == 1:
            if agreed is not None:
                return Violation(
                    reason="r1_unexpected_convergence",
                    detail="Round 1 is a silent initial round — do not emit CONVERGED.",
                )
            if questions:
                return Violation(
                    reason="r1_unexpected_questions",
                    detail="Round 1 is silent — do not ask questions yet.",
                )
            return ValidationOk()

        if round_num == 2:
            if agreed is not None:
                return Violation(
                    reason="r2_unexpected_convergence",
                    detail="Round 2 is cross-examination — do not emit CONVERGED yet.",
                )
            if len(questions) == 0:
                return Violation(
                    reason="r2_missing_question",
                    detail="Round 2 requires exactly one question of one peer.",
                )
            if len(questions) > 1:
                return Violation(
                    reason="r2_multiple_questions",
                    detail="Round 2 allows only one question — pick the most important one.",
                )
            return ValidationOk()

        # round_num >= 3
        if agreed is None:
            return Violation(
                reason="rn_missing_convergence",
                detail="Round 3+ requires exactly one of CONVERGED: yes or CONVERGED: no.",
            )
        if agreed is True:
            # questions dropped-with-warn by DebateService; not a violation.
            return ValidationOk()
        # agreed is False
        if len(questions) == 0:
            return Violation(
                reason="rn_no_converged_missing_question",
                detail="If CONVERGED: no, you must ask exactly one question of a peer.",
            )
        if len(questions) > 1:
            return Violation(
                reason="rn_multiple_questions",
                detail="Round 3+ allows only one question — pick the most important one.",
            )
        return ValidationOk()
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_validation.py -v`
Expected: all PASS.

- [ ] **Step 5: Format and commit**

```bash
ruff format council/ tests/
git add council/domain/validation.py tests/unit/test_validation.py
git commit -m "feat(domain): add TurnValidator for per-phase debate contract"
```

---

## Task 5: Rewrite `PromptBuilder` into conversation-aware methods

**Files:**
- Modify: `council/domain/prompting.py`
- Modify: `tests/unit/test_prompting.py`

- [ ] **Step 1: Review the current file for helpers to reuse**

Run: `sed -n '1,50p' council/domain/prompting.py && sed -n '51,160p' council/domain/prompting.py`
Expected: you'll see `_header`, `_own_previous_answer`, `_other_advisors_section`, `_user_messages_section`, `_directed_questions_section`, `_other_questions_section` — the first two are dropped; the rest are reused.

- [ ] **Step 2: Write failing tests for new methods**

Rewrite `tests/unit/test_prompting.py`. Replace the existing `TestRoundOne` / `TestRoundTwoPlus` classes with new tests for the new API. Keep the existing helpers `_answer`, `_debate` at the top. Delete obsolete tests that assert on removed constants.

```python
class TestBuildSystemMessage:
    def test_empty_when_no_persona_or_context(self, builder):
        assert builder.build_system_message(_debate(), "claude") == ""

    def test_persona_only(self, builder):
        pack = CouncilPack(name="p", shared_context=None, personas={"claude": "You are a lawyer."})
        assert "lawyer" in builder.build_system_message(_debate(pack=pack), "claude")

    def test_shared_context_only(self, builder):
        pack = CouncilPack(name="p", shared_context="You are my chief of staff.", personas={})
        out = builder.build_system_message(_debate(pack=pack), "claude")
        assert "chief of staff" in out

    def test_both_combined(self, builder):
        pack = CouncilPack(name="p", shared_context="Chief.", personas={"claude": "Lawyer."})
        out = builder.build_system_message(_debate(pack=pack), "claude")
        assert "Lawyer" in out
        assert "Chief" in out


class TestBuildRoundOneUser:
    def test_includes_question(self, builder):
        out = builder.build_round_1_user(_debate("Should I ship?"))
        assert "Should I ship?" in out

    def test_forbids_convergence_and_questions(self, builder):
        out = builder.build_round_1_user(_debate())
        assert "CONVERGED" not in out
        assert "QUESTIONS:" not in out

    def test_instructs_initial_take(self, builder):
        out = builder.build_round_1_user(_debate())
        assert "initial take" in out.lower()


class TestBuildRoundTwoUser:
    def _with_round_1(self):
        r1 = Round(number=1, turns=[
            Turn(elder="claude", answer=_answer("claude", "Claude R1", agreed=None)),
            Turn(elder="gemini", answer=_answer("gemini", "Gemini R1", agreed=None)),
            Turn(elder="chatgpt", answer=_answer("chatgpt", "ChatGPT R1", agreed=None)),
        ])
        return _debate(rounds=[r1])

    def test_includes_other_advisors(self, builder):
        out = builder.build_round_2_user(self._with_round_1(), "claude")
        assert "Gemini R1" in out
        assert "ChatGPT R1" in out
        assert "Claude R1" not in out  # elder doesn't need to see its own

    def test_requires_exactly_one_question(self, builder):
        out = builder.build_round_2_user(self._with_round_1(), "claude")
        assert "QUESTIONS:" in out
        assert "exactly one" in out.lower() or "one question" in out.lower()

    def test_forbids_convergence(self, builder):
        out = builder.build_round_2_user(self._with_round_1(), "claude")
        assert "CONVERGED" not in out


class TestBuildRoundNUser:
    def _debate_with_history(self):
        r1 = Round(number=1, turns=[
            Turn(elder="claude", answer=_answer("claude", "Claude R1", agreed=None)),
            Turn(elder="gemini", answer=_answer("gemini", "Gemini R1", agreed=None)),
            Turn(elder="chatgpt", answer=_answer("chatgpt", "ChatGPT R1", agreed=None)),
        ])
        q = ElderQuestion(from_elder="gemini", to_elder="claude", text="Why SSE?", round_number=2)
        r2 = Round(number=2, turns=[
            Turn(elder="claude", answer=_answer("claude", "Claude R2", agreed=None)),
            Turn(elder="gemini", answer=_answer("gemini", "Gemini R2", agreed=None), questions=(q,)),
            Turn(elder="chatgpt", answer=_answer("chatgpt", "ChatGPT R2", agreed=None)),
        ])
        return _debate(rounds=[r1, r2])

    def test_includes_previous_round_other_advisors(self, builder):
        out = builder.build_round_n_user(self._debate_with_history(), "claude", 3)
        assert "Gemini R2" in out
        assert "ChatGPT R2" in out

    def test_omits_own_previous_answer(self, builder):
        # Previous answer lives in conversation history; it should NOT be re-stuffed
        # into the user message.
        out = builder.build_round_n_user(self._debate_with_history(), "claude", 3)
        assert "Claude R2" not in out

    def test_includes_directed_questions(self, builder):
        out = builder.build_round_n_user(self._debate_with_history(), "claude", 3)
        assert "Why SSE?" in out

    def test_convergence_contract_wording(self, builder):
        out = builder.build_round_n_user(self._debate_with_history(), "claude", 3)
        assert "CONVERGED: yes" in out
        assert "CONVERGED: no" in out
        # The "no" branch demands a question.
        assert "QUESTIONS:" in out


class TestBuildRetryReminder:
    def test_contains_violation_reason(self, builder):
        out = builder.build_retry_reminder("Round 2 requires exactly one question.")
        assert "Round 2 requires exactly one question." in out

    def test_asks_for_re_send(self, builder):
        out = builder.build_retry_reminder("anything")
        assert "re-send" in out.lower() or "resend" in out.lower() or "again" in out.lower()
```

(Delete `ElderQuestion`'s import if duplicated; the existing test already imports it.)

- [ ] **Step 3: Run to confirm failures**

Run: `pytest tests/unit/test_prompting.py -v`
Expected: multiple FAIL — methods don't exist.

- [ ] **Step 4: Rewrite `prompting.py`**

Replace the entire body of `council/domain/prompting.py` with:

```python
from __future__ import annotations

from council.domain.models import Debate, ElderId

_ELDER_LABEL: dict[ElderId, str] = {
    "claude": "Claude",
    "gemini": "Gemini",
    "chatgpt": "ChatGPT",
}


class PromptBuilder:
    # ---- per-phase user-message builders --------------------------------

    def build_system_message(self, debate: Debate, elder: ElderId) -> str:
        lines: list[str] = []
        persona = debate.pack.personas.get(elder)
        if persona:
            lines.append(persona.strip())
        if debate.pack.shared_context:
            lines.append(debate.pack.shared_context.strip())
        return "\n\n".join(lines)

    def build_round_1_user(self, debate: Debate) -> str:
        return (
            f"Question: {debate.prompt}\n\n"
            "Give your initial take. Do not tag convergence or ask questions — "
            "this is a silent initial round before you see the other advisors."
        )

    def build_round_2_user(self, debate: Debate, elder: ElderId) -> str:
        parts: list[str] = []
        others = self._other_advisors_section(debate, elder, round_num=2)
        if others:
            parts.append(others)
        user_section = self._user_messages_section(debate)
        if user_section:
            parts.append(user_section)
        parts.append(
            "You have now seen the other advisors. This is the cross-examination round.\n\n"
            "You MUST end your reply with EXACTLY ONE question of EXACTLY ONE peer, "
            "formatted as:\n\n"
            "QUESTIONS:\n"
            "@<peer> your question here\n\n"
            "Where <peer> is one of: @claude, @gemini, @chatgpt (but not yourself).\n"
            "Do NOT emit a CONVERGED tag; convergence is not yet possible."
        )
        return "\n\n".join(parts)

    def build_round_n_user(self, debate: Debate, elder: ElderId, round_num: int) -> str:
        parts: list[str] = []
        others = self._other_advisors_section(debate, elder, round_num=round_num)
        if others:
            parts.append(others)
        user_section = self._user_messages_section(debate)
        if user_section:
            parts.append(user_section)
        directed = self._directed_questions_section(debate, elder, round_num)
        if directed:
            parts.append(directed)
        peer_qs = self._other_questions_section(debate, elder, round_num)
        if peer_qs:
            parts.append(peer_qs)
        parts.append(
            "End your reply with EXACTLY ONE of:\n\n"
            "(a) CONVERGED: yes — if you would not change your position after everything said.\n\n"
            "(b) CONVERGED: no, followed immediately by a QUESTIONS: block:\n\n"
            "    QUESTIONS:\n"
            "    @<peer> your probe here\n\n"
            "If you emit CONVERGED: no, you MUST ask exactly one question of one peer."
        )
        return "\n\n".join(parts)

    def build_retry_reminder(self, violation_detail: str) -> str:
        return (
            "Your previous reply did not follow the required format. "
            f"{violation_detail} "
            "Re-send your answer with the correct structure."
        )

    def build_synthesis(self, debate: Debate, by: ElderId) -> str:
        parts: list[str] = []
        header = self.build_system_message(debate, by)
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

    # ---- private helpers (reused across phases) -------------------------

    def _other_advisors_section(self, debate: Debate, elder: ElderId, round_num: int) -> str:
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

    def _directed_questions_section(self, debate: Debate, elder: ElderId, round_num: int) -> str:
        prior = debate.rounds[round_num - 2]
        directed: list[str] = []
        for t in prior.turns:
            for q in t.questions:
                if q.to_elder == elder:
                    directed.append(f'- From {_ELDER_LABEL[q.from_elder]}: "{q.text}"')
        if not directed:
            return ""
        return "Questions directed at you from the previous round:\n" + "\n".join(directed)

    def _other_questions_section(self, debate: Debate, elder: ElderId, round_num: int) -> str:
        prior = debate.rounds[round_num - 2]
        others: list[str] = []
        for t in prior.turns:
            for q in t.questions:
                if q.to_elder == elder:
                    continue
                others.append(
                    f'- [{_ELDER_LABEL[q.from_elder]} to {_ELDER_LABEL[q.to_elder]}]: "{q.text}"'
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

The public `build()` method is **removed**. Callers must migrate (Task 6 does this).

- [ ] **Step 5: Temporarily bridge `DebateService`**

`DebateService` currently calls `self.prompt_builder.build(debate, elder, round_num)`. Task 6 rewrites this properly. For now, add a temporary shim inside `DebateService._ask`:

Replace:
```python
prompt = self.prompt_builder.build(debate, elder_id, round_num)
```

with:
```python
if round_num == 1:
    prompt = self.prompt_builder.build_round_1_user(debate)
else:
    prompt = self.prompt_builder.build_round_n_user(debate, elder_id, round_num) if round_num >= 3 else self.prompt_builder.build_round_2_user(debate, elder_id)
```

This bridge is removed in Task 6.

- [ ] **Step 6: Run tests**

Run: `pytest tests/unit/test_prompting.py -v && pytest -q`
Expected: prompting tests all pass; some debate-service tests may fail on exact-wording assertions (that's expected — Task 7 rewrites those). If unrelated tests break, fix their prompt-string assertions to reflect the new copy.

- [ ] **Step 7: Format and commit**

```bash
ruff format council/ tests/
git add council/domain/prompting.py tests/unit/test_prompting.py council/domain/debate_service.py
git commit -m "feat(domain): rewrite PromptBuilder for per-phase conversation messages"
```

---

## Task 6: Create `DebateRules` Protocol + `DefaultRules` facade

**Files:**
- Create: `council/domain/rules.py`
- Create: `tests/unit/test_rules.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_rules.py
from datetime import datetime, timezone

import pytest

from council.domain.models import (
    CouncilPack, Debate, ElderAnswer, ElderId, ElderQuestion, Round, Turn,
)
from council.domain.rules import DefaultRules, ValidationOk, Violation


def _answer(elder, text="x", agreed=None):
    return ElderAnswer(
        elder=elder, text=text, error=None, agreed=agreed,
        created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
    )


def _debate(rounds=None):
    return Debate(
        id="d", prompt="Q?",
        pack=CouncilPack(name="bare", shared_context=None, personas={}),
        rounds=rounds or [], status="in_progress", synthesis=None,
    )


@pytest.fixture
def rules():
    return DefaultRules()


class TestDefaultRules:
    def test_user_message_dispatches_on_round_1(self, rules):
        out = rules.user_message(_debate(), "claude", 1)
        assert "initial take" in out.lower()
        assert "CONVERGED" not in out

    def test_user_message_dispatches_on_round_2(self, rules):
        r1 = Round(number=1, turns=[
            Turn(elder="claude", answer=_answer("claude", "c")),
            Turn(elder="gemini", answer=_answer("gemini", "g")),
            Turn(elder="chatgpt", answer=_answer("chatgpt", "ct")),
        ])
        out = rules.user_message(_debate([r1]), "claude", 2)
        assert "QUESTIONS:" in out
        assert "CONVERGED" not in out

    def test_user_message_dispatches_on_round_3_plus(self, rules):
        r1 = Round(number=1, turns=[
            Turn(elder="claude", answer=_answer("claude", "c")),
            Turn(elder="gemini", answer=_answer("gemini", "g")),
            Turn(elder="chatgpt", answer=_answer("chatgpt", "ct")),
        ])
        r2 = Round(number=2, turns=[
            Turn(elder="claude", answer=_answer("claude", "c2")),
            Turn(elder="gemini", answer=_answer("gemini", "g2")),
            Turn(elder="chatgpt", answer=_answer("chatgpt", "ct2")),
        ])
        out = rules.user_message(_debate([r1, r2]), "claude", 3)
        assert "CONVERGED: yes" in out

    def test_validate_ok(self, rules):
        r = rules.validate(agreed=None, questions=(), round_num=1, from_elder="claude")
        assert isinstance(r, ValidationOk)

    def test_validate_violation(self, rules):
        r = rules.validate(agreed=True, questions=(), round_num=1, from_elder="claude")
        assert isinstance(r, Violation)
        assert r.reason == "r1_unexpected_convergence"

    def test_retry_reminder_uses_violation_detail(self, rules):
        v = Violation(reason="test", detail="this is the specific reason")
        out = rules.retry_reminder(v)
        assert "this is the specific reason" in out

    def test_is_converged_delegates_to_round(self, rules):
        r = Round(number=3, turns=[
            Turn(elder="claude", answer=_answer("claude", "x", agreed=True)),
            Turn(elder="gemini", answer=_answer("gemini", "x", agreed=True)),
            Turn(elder="chatgpt", answer=_answer("chatgpt", "x", agreed=True)),
        ])
        assert rules.is_converged(r) is True

    def test_is_converged_false_when_mixed(self, rules):
        r = Round(number=3, turns=[
            Turn(elder="claude", answer=_answer("claude", "x", agreed=True)),
            Turn(elder="gemini", answer=_answer("gemini", "x", agreed=False)),
            Turn(elder="chatgpt", answer=_answer("chatgpt", "x", agreed=True)),
        ])
        assert rules.is_converged(r) is False
```

- [ ] **Step 2: Confirm failures**

Run: `pytest tests/unit/test_rules.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement rules.py**

```python
# council/domain/rules.py
from __future__ import annotations

from typing import Protocol

from council.domain.models import Debate, ElderId, ElderQuestion, Round
from council.domain.prompting import PromptBuilder
from council.domain.validation import (
    TurnValidator,
    ValidationOk,
    ValidationResult,
    Violation,
)

__all__ = [
    "DebateRules",
    "DefaultRules",
    "ValidationOk",
    "ValidationResult",
    "Violation",
]


class DebateRules(Protocol):
    """Pluggable debate-rules policy."""

    def system_message(self, debate: Debate, elder: ElderId) -> str: ...
    def user_message(self, debate: Debate, elder: ElderId, round_num: int) -> str: ...
    def retry_reminder(self, violation: Violation) -> str: ...
    def validate(
        self,
        *,
        agreed: bool | None,
        questions: tuple[ElderQuestion, ...],
        round_num: int,
        from_elder: ElderId,
    ) -> ValidationResult: ...
    def is_converged(self, rnd: Round) -> bool: ...


class DefaultRules:
    """Three-phase debate rules:
       R1 silent initial / R2 forced cross-exam / R3+ open with convergence.

    Thin facade over PromptBuilder and TurnValidator. Both internal classes
    remain independently testable; DefaultRules is the seam DebateService
    depends on.
    """

    def __init__(
        self,
        *,
        prompt_builder: PromptBuilder | None = None,
        validator: TurnValidator | None = None,
    ) -> None:
        self._prompt_builder = prompt_builder or PromptBuilder()
        self._validator = validator or TurnValidator()

    def system_message(self, debate: Debate, elder: ElderId) -> str:
        return self._prompt_builder.build_system_message(debate, elder)

    def user_message(self, debate: Debate, elder: ElderId, round_num: int) -> str:
        if round_num == 1:
            return self._prompt_builder.build_round_1_user(debate)
        if round_num == 2:
            return self._prompt_builder.build_round_2_user(debate, elder)
        return self._prompt_builder.build_round_n_user(debate, elder, round_num)

    def retry_reminder(self, violation: Violation) -> str:
        return self._prompt_builder.build_retry_reminder(violation.detail)

    def validate(
        self,
        *,
        agreed: bool | None,
        questions: tuple[ElderQuestion, ...],
        round_num: int,
        from_elder: ElderId,
    ) -> ValidationResult:
        return self._validator.validate(
            agreed=agreed,
            questions=questions,
            round_num=round_num,
            from_elder=from_elder,
        )

    def is_converged(self, rnd: Round) -> bool:
        return rnd.converged()
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_rules.py -v`
Expected: PASS.

- [ ] **Step 5: Format and commit**

```bash
ruff format council/ tests/
git add council/domain/rules.py tests/unit/test_rules.py
git commit -m "feat(domain): DebateRules Protocol + DefaultRules facade"
```

---

## Task 7: Rewrite `DebateService` — rules + conversations + retry

**Files:**
- Modify: `council/domain/debate_service.py`
- Modify: `tests/unit/test_debate_service.py`

- [ ] **Step 1: Write failing tests for conversation growth and retry**

Add the following to `tests/unit/test_debate_service.py` (keep existing tests; update assertions that assume the old prompt shape). New tests:

```python
# Append to the existing test module:

from council.domain.models import Message
from council.domain.rules import DefaultRules, Violation


class _ScriptedPort:
    """ElderPort stub that returns pre-scripted replies in order, and
    captures every conversation it was called with."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.calls: list[list[Message]] = []

    async def ask(self, conversation, *, timeout_s=45.0) -> str:
        # snapshot the conversation at call time (it mutates afterwards)
        self.calls.append(list(conversation))
        return self._replies.pop(0)

    async def health_check(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_run_round_grows_conversation(tmp_store, tmp_clock, bus):
    ports = {
        "claude": _ScriptedPort(["R1 claude answer"]),
        "gemini": _ScriptedPort(["R1 gemini answer"]),
        "chatgpt": _ScriptedPort(["R1 chatgpt answer"]),
    }
    svc = DebateService(elders=ports, store=tmp_store, clock=tmp_clock, bus=bus)
    debate = _new_debate("What?")
    await svc.run_round(debate)

    # Claude's conversation should be [user_r1, assistant_r1] (no system since
    # pack is bare).
    conv = svc.conversations["claude"]
    assert len(conv) == 2
    assert conv[0].role == "user"
    assert "What?" in conv[0].content
    assert conv[1] == Message("assistant", "R1 claude answer")


@pytest.mark.asyncio
async def test_run_round_retries_on_violation(tmp_store, tmp_clock, bus):
    # R2 requires a question. First reply has none — expect a retry.
    bad_r2 = "Just my thoughts, no question."
    good_r2 = "My thoughts.\n\nQUESTIONS:\n@gemini why?"
    ports = {
        "claude": _ScriptedPort(["R1 answer", bad_r2, good_r2]),
        "gemini": _ScriptedPort(["R1 gemini", "Gemini R2\n\nQUESTIONS:\n@claude why?"]),
        "chatgpt": _ScriptedPort(["R1 chatgpt", "ChatGPT R2\n\nQUESTIONS:\n@gemini why?"]),
    }
    svc = DebateService(elders=ports, store=tmp_store, clock=tmp_clock, bus=bus)
    debate = _new_debate("Q?")
    await svc.run_round(debate)   # R1
    await svc.run_round(debate)   # R2 — Claude retries

    # Claude was asked twice in R2 (once bad, once after retry reminder).
    assert len(ports["claude"].calls) == 3  # R1 + bad R2 + retry R2
    # Second R2 call includes a "user" retry-reminder turn.
    retry_call = ports["claude"].calls[2]
    assert retry_call[-1].role == "user"
    assert "did not follow" in retry_call[-1].content.lower() or "re-send" in retry_call[-1].content.lower()


@pytest.mark.asyncio
async def test_run_round_retry_ceiling(tmp_store, tmp_clock, bus):
    # Both R2 attempts fail the contract — turn built best-effort, no third call.
    ports = {
        "claude": _ScriptedPort(["R1", "no q here", "still no q"]),
        "gemini": _ScriptedPort(["R1", "G\n\nQUESTIONS:\n@claude why?"]),
        "chatgpt": _ScriptedPort(["R1", "C\n\nQUESTIONS:\n@gemini why?"]),
    }
    svc = DebateService(elders=ports, store=tmp_store, clock=tmp_clock, bus=bus)
    debate = _new_debate("Q?")
    await svc.run_round(debate)
    await svc.run_round(debate)
    # Exactly 3 calls to claude: R1, bad R2, retry R2. No third R2 call.
    assert len(ports["claude"].calls) == 3
```

You may need to add `tmp_store`, `tmp_clock`, `bus`, `_new_debate` fixtures if they don't exist — or adapt to whatever is already in `conftest.py` / the test module.

- [ ] **Step 2: Confirm failures**

Run: `pytest tests/unit/test_debate_service.py -v`
Expected: new tests FAIL; some existing tests may also fail because `DebateService` signature is about to change. That's expected.

- [ ] **Step 3: Rewrite `DebateService`**

Update `council/domain/debate_service.py`:

```python
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from council.domain.convergence import ConvergencePolicy
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
    Message,
    Round,
    Turn,
    UserMessage,
)
from council.domain.ports import Clock, ElderPort, EventBus, TranscriptStore
from council.domain.prompting import PromptBuilder
from council.domain.questions import QuestionParser
from council.domain.rules import DebateRules, DefaultRules, Violation

log = logging.getLogger(__name__)


@dataclass
class DebateService:
    elders: dict[ElderId, ElderPort]
    store: TranscriptStore
    clock: Clock
    bus: EventBus
    rules: DebateRules = field(default_factory=DefaultRules)
    prompt_builder: PromptBuilder = field(default_factory=PromptBuilder)
    convergence: ConvergencePolicy = field(default_factory=ConvergencePolicy)
    question_parser: QuestionParser = field(default_factory=QuestionParser)
    conversations: dict[ElderId, list[Message]] = field(default_factory=dict)

    async def run_round(self, debate: Debate) -> Round:
        round_num = len(debate.rounds) + 1

        async def _ask(elder_id: ElderId) -> Turn:
            port = self.elders[elder_id]
            conv = self.conversations.setdefault(elder_id, [])

            # Step 1-2: append the next user message (and system on first round).
            if not conv:
                system_text = self.rules.system_message(debate, elder_id)
                if system_text:
                    conv.append(Message("system", system_text))
            conv.append(Message("user", self.rules.user_message(debate, elder_id, round_num)))

            await self.bus.publish(TurnStarted(elder=elder_id, round_number=round_num))

            try:
                raw = await port.ask(conv)
            except asyncio.TimeoutError:
                err = ElderError(elder=elder_id, kind="timeout", detail="")
                ans = self._error_answer(elder_id, err)
                await self.bus.publish(TurnFailed(elder=elder_id, round_number=round_num, error=err))
                return Turn(elder=elder_id, answer=ans)
            except Exception as ex:
                kind = getattr(ex, "kind", "nonzero_exit")
                detail = getattr(ex, "detail", repr(ex))
                err = ElderError(elder=elder_id, kind=kind, detail=detail)
                ans = self._error_answer(elder_id, err)
                await self.bus.publish(TurnFailed(elder=elder_id, round_number=round_num, error=err))
                return Turn(elder=elder_id, answer=ans)

            # Steps 4-6: parse and validate.
            cleaned, agreed = self.convergence.parse(raw)
            cleaned2, questions = self.question_parser.parse(
                cleaned, from_elder=elder_id, round_number=round_num
            )
            result = self.rules.validate(
                agreed=agreed, questions=questions,
                round_num=round_num, from_elder=elder_id,
            )

            final_raw = raw

            # Step 7: retry once on contract violation.
            if isinstance(result, Violation):
                conv.append(Message("assistant", raw))
                conv.append(Message("user", self.rules.retry_reminder(result)))
                try:
                    raw2 = await port.ask(conv)
                except Exception:
                    # Retry blew up adapter-level — surface as a TurnFailed.
                    raise
                cleaned, agreed = self.convergence.parse(raw2)
                cleaned2, questions = self.question_parser.parse(
                    cleaned, from_elder=elder_id, round_number=round_num
                )
                final_raw = raw2
                # Accept whatever; one retry ceiling. Log if still invalid.
                post_result = self.rules.validate(
                    agreed=agreed, questions=questions,
                    round_num=round_num, from_elder=elder_id,
                )
                if isinstance(post_result, Violation):
                    log.warning(
                        "Elder %s round %s still violates contract after retry: %s",
                        elder_id, round_num, post_result.reason,
                    )

            # Step 8: phase-specific drop-with-warn.
            if round_num == 1:
                if agreed is not None or questions:
                    log.warning(
                        "Elder %s round 1 emitted unexpected convergence/questions; dropping.",
                        elder_id,
                    )
                agreed = None
                questions = ()
            elif round_num >= 3 and agreed is True and questions:
                log.warning(
                    "Elder %s round %s emitted CONVERGED: yes with questions; dropping questions.",
                    elder_id, round_num,
                )
                questions = ()

            # Step 9: record assistant reply.
            conv.append(Message("assistant", final_raw))

            # Step 10: build Turn.
            ans = ElderAnswer(
                elder=elder_id,
                text=cleaned2,
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

        turns = await asyncio.gather(*(_ask(eid) for eid in self.elders.keys()))
        r = Round(number=round_num, turns=list(turns))
        debate.rounds.append(r)
        self.store.save(debate)
        await self.bus.publish(RoundCompleted(round=r))
        return r

    async def synthesize(self, debate: Debate, by: ElderId) -> ElderAnswer:
        port = self.elders[by]
        prompt_text = self.prompt_builder.build_synthesis(debate, by=by)
        conversation = [Message("user", prompt_text)]
        try:
            raw = await port.ask(conversation)
            ans = ElderAnswer(
                elder=by,
                text=raw.strip(),
                error=None,
                agreed=None,
                created_at=self.clock.now(),
            )
        except Exception as ex:
            kind = getattr(ex, "kind", "nonzero_exit")
            detail = getattr(ex, "detail", repr(ex))
            err = ElderError(elder=by, kind=kind, detail=detail)
            ans = self._error_answer(by, err)
        debate.synthesis = ans
        debate.status = "synthesized"
        self.store.save(debate)
        await self.bus.publish(SynthesisCompleted(answer=ans))
        return ans

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

    def _error_answer(self, elder_id: ElderId, err: ElderError) -> ElderAnswer:
        return ElderAnswer(
            elder=elder_id,
            text=None,
            error=err,
            agreed=None,
            created_at=self.clock.now(),
        )
```

- [ ] **Step 4: Run all unit tests**

Run: `pytest tests/unit -q`
Expected: all pass. Fix any broken existing tests by updating their prompt-assertion strings; the semantics haven't changed.

- [ ] **Step 5: Format + commit**

```bash
ruff format council/ tests/
git add council/domain/debate_service.py tests/unit/test_debate_service.py
git commit -m "feat(domain): DebateService consumes DebateRules, keeps per-elder conversations"
```

---

## Task 8: TUI — R1+R2 auto-chain + auto-synth on convergence

**Files:**
- Modify: `council/app/tui/app.py`
- Modify: `tests/e2e/test_tui_full_debate.py`
- Modify: `tests/e2e/test_tui_elder_questions.py`

- [ ] **Step 1: Auto-chain R1→R2 on initial submit**

In `council/app/tui/app.py`, `_on_input_submitted` first-submission branch — change:

```python
self._spawn(self._service.run_round(self._debate))
```

to a helper that runs R1, waits for it to complete via the bus, then runs R2:

```python
self.run_worker(self._opening_exchange_worker(), exclusive=True)
```

And add the worker method on the `CouncilApp` class:

```python
async def _opening_exchange_worker(self) -> None:
    if self._debate is None:
        return
    # R1 — await it by pushing through the service directly (no awaiting
    # the bus, just the coroutine result).
    await self._service.run_round(self._debate)
    # R2 auto-chains.
    await self._service.run_round(self._debate)
```

Note: the existing `_consume_events` handler for `RoundCompleted` will set `awaiting_decision = True` after each round. That's fine for R2 (we WANT the user free after R2), but we need it NOT to re-enable input between R1 and R2.

Fix: add a guard in `_consume_events` so that during the opening exchange, `awaiting_decision` and input-enable only happen after round 2:

```python
elif isinstance(ev, RoundCompleted):
    # Opening exchange (R1+R2) runs back-to-back; only re-enable input
    # after the *second* round completes.
    if ev.round.number >= 2:
        self.awaiting_decision = True
        self.query_one("#input", CouncilInput).disabled = False
        # Auto-synth on full convergence in R3+.
        if ev.round.number >= 3 and self._service.rules.is_converged(ev.round):
            self.run_worker(self._synthesize_worker(), exclusive=True)
    if self._using_openrouter:
        self._spawn(self._write_cost_notice())
```

- [ ] **Step 2: Update e2e test `test_tui_full_debate.py`**

The existing test scripts R1 replies and expects the round to be the end of the interactive exchange. Update:

- Script R1 replies for all three elders (silent initial — no CONVERGED, no QUESTIONS).
- Script R2 replies for all three elders — each with a valid `QUESTIONS: @peer ...` block.
- Then press `c` for R3.
- Script R3 replies — 2×`CONVERGED: no` + question, 1×`CONVERGED: yes`.
- Press `c` for R4.
- Script R4 replies — all three `CONVERGED: yes`.
- Assert the synthesiser-pick modal appears.
- Pick a synthesiser; script synthesis reply; assert it renders.

Adjust the test's `_FakeElder.ask` stub (or similar) so it returns from a queue. Read the existing file first:

```bash
sed -n '1,120p' tests/e2e/test_tui_full_debate.py
```

Then rewrite the replies-queue and the assertions to match the new flow.

- [ ] **Step 3: Update `test_tui_elder_questions.py`**

In the existing test, R2 is now where questions first appear (not optional). Update scripted replies so R1 is silent and R2 has the questions. Adjust assertions about when the question-rendering is expected.

- [ ] **Step 4: Run the TUI e2e tests**

Run: `pytest tests/e2e/test_tui_full_debate.py tests/e2e/test_tui_elder_questions.py -v`
Expected: PASS.

- [ ] **Step 5: Format + commit**

```bash
ruff format council/ tests/
git add council/app/tui/app.py tests/e2e/test_tui_full_debate.py tests/e2e/test_tui_elder_questions.py
git commit -m "feat(tui): R1+R2 opening exchange auto-chain; auto-synth modal on full convergence"
```

---

## Task 9: Headless — R1+R2 auto + `--max-rounds` flag

**Files:**
- Modify: `council/app/headless/main.py`
- Modify: `tests/e2e/test_headless_flow.py`

- [ ] **Step 1: Write failing test**

Extend `tests/e2e/test_headless_flow.py` to verify the new behaviour:

```python
def test_headless_runs_r1_r2_then_synth_by_default():
    # Script three silent R1s + three R2s-with-questions + synthesis.
    # Assert two rounds were run, then synthesis, then cost line.
    ...


def test_headless_respects_max_rounds():
    # --max-rounds 4 + scripted replies that never converge.
    # Assert exactly 4 rounds were run, then synthesis.
    ...


def test_headless_early_terminates_on_convergence():
    # --max-rounds 6 + scripted replies where all converge in R3.
    # Assert only 3 rounds were run.
    ...


def test_headless_rejects_max_rounds_below_2():
    # Invoke main with --max-rounds 1 → argparse error.
    ...
```

Follow the existing test file's patterns for scripted adapters and main() invocation.

- [ ] **Step 2: Confirm failures**

Run: `pytest tests/e2e/test_headless_flow.py -v`
Expected: new tests FAIL; existing one-round test may also fail.

- [ ] **Step 3: Update `headless/main.py`**

```python
# Replace the argparse block — add --max-rounds with validation:
def _max_rounds_type(value: str) -> int:
    n = int(value)
    if n < 2:
        raise argparse.ArgumentTypeError("--max-rounds must be at least 2")
    return n

parser.add_argument(
    "--max-rounds",
    type=_max_rounds_type,
    default=3,
    help="Upper bound on total rounds (including R1+R2). Minimum 2; default 3.",
)
```

And replace the `run_headless` body's round-running section:

```python
svc = DebateService(elders=elders, store=store, clock=clock, bus=bus)

# Opening exchange — always R1 + R2.
await svc.run_round(debate)
await svc.run_round(debate)

# R3+ until convergence or max-rounds.
while len(debate.rounds) < max_rounds and not svc.rules.is_converged(debate.rounds[-1]):
    await svc.run_round(debate)

# Print each round in order (or just final-round summary — preserve existing
# logging shape). Then synthesise:
synth = await svc.synthesize(debate, by=synthesizer)
# ...cost line unchanged
```

Pass `max_rounds` from the argparse args into `run_headless` (add the parameter).

- [ ] **Step 4: Run tests**

Run: `pytest tests/e2e/test_headless_flow.py -v && pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
ruff format council/ tests/
git add council/app/headless/main.py tests/e2e/test_headless_flow.py
git commit -m "feat(headless): R1+R2 auto-chain + --max-rounds flag (default 3)"
```

---

## Task 10: Docs — README + USAGE

**Files:**
- Modify: `README.md`
- Modify: `docs/USAGE.md`

- [ ] **Step 1: Rewrite the "Participating in the debate" section in README.md**

Read the current section first:

```bash
grep -n "Participating in the debate" README.md
```

Replace with a description of the three phases:

```markdown
## How the debate unfolds

The council runs a structured three-phase debate so the elders actually engage rather than producing three parallel monologues:

**Round 1 — Silent initial answers.** Each elder answers your question independently, without seeing the others. No convergence, no cross-talk.

**Round 2 — Cross-examination (auto-runs after round 1).** Each elder now sees the other two's round-1 answers and must ask exactly one question of one peer (`@claude`, `@gemini`, or `@chatgpt`). Convergence is still not possible — this is dialogue first.

**Round 3 and beyond — Open debate.** Each elder either says `CONVERGED: yes` (they'd not change their view) or `CONVERGED: no` and asks exactly one further question of a peer. You press `c` to trigger each round. When all three converge in the same round, you're prompted to pick a synthesiser automatically.

Converged elders stay in the conversation. If a peer directs a question at you after you converged, you see it in your next turn and can either hold your position or change your mind.

You can always press `s` to synthesise early, or type between rounds to inject a clarifying question or direction.
```

Update the keybindings table entry for `c`:

```markdown
| `c` | Continue another round (available after round 2, while elders haven't all converged) |
```

- [ ] **Step 2: Add a "How the debate mechanic works" section to docs/USAGE.md**

Append a substantial section covering:
- The three-phase model and why it was designed this way (briefly summarise the "consensus too fast" problem the old model had).
- The convergence contract (yes = I'd not change my view; no = I must probe).
- The retry behaviour (one sharpened retry per contract violation; silent best-effort on stubborn models).
- The auto-synthesise-on-full-convergence behaviour.
- How user messages and elder-to-elder questions interact with phases.
- Elder conversation memory (each elder now maintains a real multi-turn conversation; OpenRouter uses native multi-turn; CLI adapters flatten for the same effect).

Keep it practical, ≈ 40-80 lines of prose.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/USAGE.md
git commit -m "docs: update README + USAGE for three-phase debate model"
```

---

## Task 11: Final end-to-end smoke

- [ ] **Step 1: Run full suite**

Run: `pytest -q`
Expected: all tests pass; no regressions.

- [ ] **Step 2: Run lint + format checks**

Run: `ruff format --check council/ tests/ && ruff check council/ tests/`
Expected: All checks passed.

- [ ] **Step 3: Optional — run the TUI locally, end-to-end**

If `$OPENROUTER_API_KEY` is set: `council --pack bare` (or `council-headless "what is 2+2?" --max-rounds 3`). Observe R1+R2 auto-chain, then press `c` for R3, verify convergence ends the debate.

- [ ] **Step 4: Push**

```bash
git push
```

Wait for CI to pass on both Python 3.12 and 3.13.

# Debate Model Redesign — Design

**Date:** 2026-04-19
**Status:** Approved (pending implementation plan)

## Problem

Across ten real debates saved under `~/.council/debates/` — including a four-round one — zero inter-elder questions have ever been produced. Worse, the underlying behaviour is not just "no questions":

- In Round 1, every elder marks `CONVERGED: yes` before seeing any other elder's answer. The tag is effectively reporting "I'm happy with my own answer", not real agreement.
- Elders produce parallel monologues. Claude does not quote Gemini; Gemini ignores Claude; ChatGPT closes with "If you want, I can also give you…" as if it were a solo chat.
- When an elder does flag `agreed=False` (Gemini, occasionally), the "response" is to regenerate its own options — no probe, no engagement.

The debate is mechanically three parallel streams of LLM output with a post-hoc convergence check. The prompts encode this: `_QUESTIONS_INSTRUCTION` begins with the word "optionally" (`council/domain/prompting.py:13-19`), and the round-2+ framing is "you may revise your answer or stand by it" (`council/domain/prompting.py:64`) — both push toward entrenchment, not dialogue.

This redesign restructures the debate so dialogue is **required** and convergence is only possible after real engagement has happened.

## Goals

- Force a real cross-examination step every debate, not an opt-in.
- Prevent convergence being claimed before any debate has occurred (the current R1 failure mode).
- Make the convergence contract crisp: either you're done, or you're still probing — no in-between.
- Give each elder a proper multi-turn conversation with memory, not a series of stateless single-shot prompts — so elders see their own prior reasoning as context, per-round prompts shrink, and OpenRouter prompt caching kicks in.
- Preserve existing user capabilities: between-rounds message injection, `c`/`s`/`a`/`o` keybindings, pack personas, OpenRouter and CLI transport parity.

## Non-goals

- Changing the elder-count model (still three: claude/gemini/chatgpt). The "arbitrary models" brainstorm is a separate spec.
- Streaming, branching, forking debates.
- Variable retry budgets — one retry per violation, no more.
- Migrating existing saved debates' transcripts to the new contract. They remain as-is; only new turns are validated.
- Changing synthesis prompting or the synthesiser-picker UX.
- Persisting per-elder conversation state across sessions. Conversations are rebuilt in memory at session start from the saved `Turn` records and discarded when the session ends. Resuming a persisted debate is not a supported flow today anyway.

## Phase model

The debate now has three phases keyed off `round.number`.

| Phase | Rounds | `CONVERGED:` allowed | Question requirement | Trigger |
|---|---|---|---|---|
| Silent initial | 1 | No | No | User submits prompt |
| Cross-examination | 2 | No | Exactly one per elder, targeting one peer | Auto-chains after R1 |
| Open debate | ≥3 | Required (`yes` or `no`) | Exactly one per elder *if* `CONVERGED: no`; none if `CONVERGED: yes` | User presses `c` |

**Auto-termination:** if every elder emits `CONVERGED: yes` in the same round, the TUI shows the synthesiser-pick prompt automatically (same affordance as pressing `s`). The user may still press `s` earlier.

**Converged elders stay in the conversation.** Every elder runs every round. If an elder said `CONVERGED: yes` in round N and a peer directs a question at them in round N+1, they see that question in their next prompt and may either hold (`CONVERGED: yes` again, optionally addressing the question in prose) or flip (`CONVERGED: no` + one question of their own).

### Flow

```
[user prompt]
     │
     ▼
 Round 1 (silent initial) ──auto──▶ Round 2 (forced cross-exam)
                                         │
                                         ▼
                                   await user: c / s / input
                                         │
                          c ──▶ Round 3+ (open, CONVERGED-capable)
                                         │
                                         ▼
                          all 3 CONVERGED: yes ──▶ prompt synthesiser pick
                                         │
                          not all yes ──▶ await user again
```

## Elder conversation memory

Today `ElderPort.ask(prompt: str) -> str` is stateless: each round is a single-shot call, and `PromptBuilder` re-stuffs "your previous answer" / "other advisors said" / directed-questions / user-messages into every round's prompt. The elder literally cannot see its own prior reasoning — only a paraphrase we pasted in.

This redesign treats each elder as a proper multi-turn chat. One conversation per elder per debate. The conversation is accumulated in `DebateService` memory across rounds and handed to the adapter on every `ask()` call.

**Conversation shape** — a `Message` NamedTuple exported from `council/domain/models.py`:

```python
from typing import Literal, NamedTuple

Role = Literal["system", "user", "assistant"]

class Message(NamedTuple):
    role: Role
    content: str
```

Stored as a `list[Message]` per elder. `NamedTuple` gives us structural tuple access (`role, content = msg`), hashability, and immutability without dragging in dataclass boilerplate.

**What lives where:**

| Content | Lives in | Emitted when |
|---|---|---|
| Elder persona + shared pack context | `system` message at index 0 | Once, at conversation start |
| Original user question + R1 instruction | First `user` message | Once, at conversation start |
| Elder's own reply (raw, including CONVERGED/QUESTIONS tail) | `assistant` message after each round | After every `ask()` |
| Other advisors' answers from prior round | Next `user` message | Every round ≥ 2 |
| Questions directed at *this* elder from prior round | Next `user` message | Every round ≥ 2 |
| Other peer cross-talk from prior round | Next `user` message | Every round ≥ 2 |
| User-as-elder messages since last round | Next `user` message | Round after each user msg |
| Phase-specific instruction (R1/R2/R3+ contract reminder) | Tail of next `user` message | Every round |

**What drops out of per-round prompts** (compared to today): the "Your previous answer:" section (the model remembers via assistant history), and the re-pasted original question header each round (it's already in the first user turn).

**What gets shorter** per-round: the total prompt. Measured naively, per-round tokens drop by roughly one full prior-answer copy (≈ 300–1500 tokens depending on answer length). OpenRouter/Anthropic prompt caching on the stable prefix (`system` + first `user` + early turns) amortises further cost across later rounds.

**Adapter behaviour:**

- **`OpenRouterAdapter`** — passes the conversation verbatim as the `messages` array to `/v1/chat/completions`. No string flattening. System turn goes in with `role: "system"`. Enables OpenRouter's built-in prompt caching. Trivial change: ~5 lines in `ask()`.
- **`ClaudeCodeAdapter` / `GeminiCLIAdapter` / `CodexCLIAdapter`** — the vendor CLIs' non-interactive modes (`claude -p`, `gemini -p`, `codex exec`) are one-shot, single-prompt. We flatten the conversation into a single text blob and pass it as the prompt, using role-tagged sections:

  ```
  SYSTEM:
  <persona + shared context>

  USER:
  <first user message>

  ASSISTANT:
  <elder's round-1 reply, raw>

  USER:
  <round-2 user message — other advisors + instructions>

  ASSISTANT:
  <elder's round-2 reply, raw>

  USER:
  <round-3 user message>
  ```

  This is not a *true* multi-turn conversation (the CLI spawns a fresh model invocation), but the model sees the same content and reasons over it the same way. No vendor-CLI interface change, no new dependency.

**Persistence:** no schema change. The conversation is derivable from `Turn.answer.text` + the per-round prompt inputs, but because cleaned text differs from raw (CONVERGED/QUESTIONS stripped), we keep conversation state **in-memory only** for the duration of a session. Resuming a persisted debate (not a supported flow today) would see clean-text-based history; fine for backward compatibility.

**ElderPort contract change:** `ask(prompt: str) -> str` becomes `ask(conversation: list[Message]) -> str`. The simple `list[Message]` type is imported from `council.domain.models`. All four adapters are updated. Contract tests are updated.

## Components

### `council/domain/prompting.py` — conversation-aware message builders

The single `build()` method is replaced by four smaller, conversation-oriented builders. Each produces raw strings that `DebateService` packages into `Message` tuples.

- **`build_system_message(debate, elder) -> str`** — persona + shared pack context. Empty string if neither is set (in which case `DebateService` omits the system turn entirely). Called once per elder per debate.
- **`build_round_1_user(debate) -> str`** — `Question: <prompt>` + `"Give your initial take. Do not tag convergence or ask questions — this is a silent initial round."` Called once per elder per debate.
- **`build_round_2_user(debate, elder) -> str`** — "Other advisors said:" block (R1 answers from the other two elders) + any user-as-elder messages + `"You must end with:\n\nQUESTIONS:\n@<target> <your question>\n\n— exactly one question, directed at @claude, @gemini, or @chatgpt (not yourself). Do not emit a CONVERGED tag; this is not yet a convergence round."`
- **`build_round_n_user(debate, elder, round_num) -> str`** (n ≥ 3) — "Other advisors said:" from previous round + user-as-elder messages since last round + "Questions directed at you:" + "Other peer questions:" + `"You may revise your answer or stand by it. End with exactly one of:\n\n(a) CONVERGED: yes — if you would not change your position after everything said.\n\n(b) CONVERGED: no, followed immediately by:\n    QUESTIONS:\n    @<target> <your probe>\n\nIf you emit CONVERGED: no you must ask exactly one question of one peer."` **Does not include "your previous answer"** — that's already in the conversation history as an assistant turn.
- **`build_retry_reminder(violation_reason: str) -> str`** — single-paragraph sharpened reminder: `"Your previous reply did not follow the required format: <reason>. Re-send your answer with the correct structure. <terse restate of phase contract>."` Appended as an additional user turn in the retry flow.

Old constants `_QUESTIONS_INSTRUCTION` and `_CONVERGED_INSTRUCTION` are deleted. The shared helpers for sectioning (`_other_advisors_section`, `_user_messages_section`, `_directed_questions_section`, `_other_questions_section`) remain — they're now called from `build_round_n_user`. `_own_previous_answer` helper is deleted (no longer needed). `_header` is renamed to `_system_header_text` and used only by `build_system_message`.

`build_synthesis` is unchanged — synthesis is still a single-shot, full-debate-history prompt.

### `council/domain/validation.py` — new `TurnValidator`

Pure function, no I/O. Consumes the output of `ConvergencePolicy.parse` and `QuestionParser.parse` and returns `ValidationResult`.

```python
@dataclass(frozen=True)
class ValidationOk:
    pass

@dataclass(frozen=True)
class Violation:
    reason: str    # stable kind, e.g. "r2_missing_question"
    detail: str    # human-readable message for the retry prompt


ValidationResult = ValidationOk | Violation


class TurnValidator:
    def validate(
        self,
        *,
        agreed: bool | None,
        questions: tuple[ElderQuestion, ...],
        round_num: int,
        from_elder: ElderId,
    ) -> ValidationResult: ...
```

**Contract per phase:**

| Round | `agreed` | Questions | Violation reasons |
|---|---|---|---|
| 1 | MUST be `None` | MUST be 0 | `r1_unexpected_convergence` (any tag), `r1_unexpected_questions` (any questions) |
| 2 | MUST be `None` | MUST be exactly 1, to a peer, not self | `r2_unexpected_convergence`, `r2_missing_question`, `r2_multiple_questions` |
| ≥3 | MUST be `True` or `False` | if True → MUST be 0 (drop with warn); if False → MUST be exactly 1 | `rn_missing_convergence`, `rn_no_converged_missing_question`, `rn_multiple_questions` |

The validator emits at most one `Violation` per call — the first contract failure encountered. "Drop with warn" cases (e.g. questions in R1, questions alongside `CONVERGED: yes` in R3+) are not violations; they just result in the extra data being discarded by `DebateService` before `Turn` construction. "Warn" means a `logging.warning(...)` emitted by `DebateService` at the drop site, naming the elder, round, and what was dropped — visible in dev logs, not surfaced to the end user.

### `council/domain/debate_service.py` — per-elder conversations, retry branch

`DebateService` gains two new pieces of state:

1. `validator: TurnValidator = TurnValidator()` — dependency.
2. `conversations: dict[ElderId, list[Message]]` — in-memory per-elder conversation, populated lazily on first round and extended every round. Reset if `DebateService` is re-instantiated.

Per-elder loop (inside the existing `_ask` task) for round N:

```
1. conv = conversations[elder]   # list[Message], empty on first call
2. if conv is empty:
       system_text = prompt_builder.build_system_message(debate, elder)
       if system_text: conv.append(Message("system", system_text))
       conv.append(Message("user", prompt_builder.build_round_1_user(debate)))
   else:
       if N == 2:
           conv.append(Message("user", prompt_builder.build_round_2_user(debate, elder)))
       else:  # N >= 3
           conv.append(Message("user", prompt_builder.build_round_n_user(debate, elder, N)))
3. raw = await port.ask(conv)
4. cleaned, agreed = convergence.parse(raw)
5. cleaned2, questions = question_parser.parse(cleaned, from_elder=elder, round_number=N)
6. result = validator.validate(agreed=agreed, questions=questions, round_num=N, from_elder=elder)
7. if isinstance(result, Violation):
       conv.append(Message("assistant", raw))   # record what they said
       conv.append(Message("user", prompt_builder.build_retry_reminder(result.detail)))
       raw2 = await port.ask(conv)
       cleaned, agreed = convergence.parse(raw2)
       cleaned2, questions = question_parser.parse(cleaned, from_elder=elder, round_number=N)
       # Accept whatever comes back. Do NOT re-validate-and-retry; one retry ceiling.
       # If the validator would still flag it, log a warning and proceed.
8. Apply phase-specific "drop with warn" cleanup:
       - R1: discard `agreed` and `questions` (set agreed=None, questions=())
       - R3+ with agreed=True: discard `questions` (set to ())
9. conv.append(Message("assistant", final_raw))   # record the final reply in memory
10. Build Turn(answer=ElderAnswer(..., agreed=agreed, text=cleaned2, ...), questions=questions)
```

Error paths from adapters (`ElderSubprocessError`, `OpenRouterError`, `asyncio.TimeoutError`) are unchanged — they still flow into `TurnFailed` / error `Turn` as today. The retry branch only fires on **contract** violations, i.e. when the adapter returned a response but the shape is wrong.

`run_round` signature is unchanged. The service does **not** auto-chain R1→R2; that's a caller concern (see TUI / headless changes).

### `council/app/tui/app.py` — R1+R2 opening exchange, auto-synth on full convergence

New behaviour on initial prompt submission:
1. `run_round(debate)` (R1).
2. Immediately call `run_round(debate)` again (R2). TextArea stays disabled between the two.
3. After R2 completes, re-enable TextArea and user controls.

After each subsequent round (R3+):
- Check `debate.rounds[-1].converged()` (existing method on `Round`).
- If True → show the synthesiser-pick prompt (same UI as pressing `s`).
- If False → remain in between-rounds idle state.

`c` keybinding description updates to: "Continue another round (available after R2 and while elders have not all converged)."

### `council/app/headless/main.py` — bounded round loop

Headless today runs exactly one round, then synthesises. That's inadequate under the new model (R1 alone is "silent initial take" with no debate).

New flow:
1. Always run R1 and R2 (opening exchange — minimum two rounds).
2. Continue running rounds until either `debate.rounds[-1].converged()` is True, or `--max-rounds N` (new flag, default **3**) is hit. `N` counts *total* rounds including R1+R2, so the default allows one optional R3. A user who wants deeper debate can pass `--max-rounds 6`.
3. Synthesise.

Values of `N < 2` are rejected at argparse time — the opening exchange is non-optional. Cost line emission is unchanged (still a single line after synthesis).

### Adapter updates

All adapters implement the revised `ElderPort.ask(conversation: list[Message]) -> str`.

**`council/adapters/elders/openrouter.py`:**
- `ask()` takes `list[Message]`; maps directly into `{"role": role, "content": content}` dicts for the `messages` field of the POST body. System turn uses `role: "system"`. Empty conversation is an invariant violation (guarded with `assert len(conversation) >= 1`).
- Cost accounting (`session_cost_usd`, `session_tokens`) and error mapping unchanged.

**`council/adapters/elders/claude_code.py` / `gemini_cli.py` / `codex_cli.py`:**
- `ask()` takes `list[Message]`; flattens to a single prompt string before shelling out. Flattening format:
  ```
  SYSTEM:
  <system content>

  USER:
  <user content>

  ASSISTANT:
  <assistant content>

  USER:
  <next user content>
  ```
  Separator between sections: two newlines. If no system turn, start with `USER:`. Final turn is always `USER:` (the current round's input).
- A new shared helper `council/adapters/elders/_flatten.py` provides `flatten_conversation(conv: list[Message]) -> str` used by all three CLI adapters. DRY.
- CLI invocation (argv, env, timeouts) unchanged.

### Persistence

No schema changes. `agreed=None` already round-trips via `JsonFileStore`. `Turn.questions` shape is unchanged. Old saved debates continue to deserialise.

Per-elder conversation state is **not** persisted. It lives on `DebateService.conversations` and is discarded at session end. This keeps the on-disk schema stable and avoids needing to version conversation format. Resuming a saved debate in a new session (not a current feature) would lose conversation memory, but all prior-round content is still recoverable from `Turn` records if we ever add that flow.

## Data flow for a single round

```
run_round(debate)
     │
     ├─ per elder (asyncio.gather):
     │     conv = self.conversations[elder]
     │     if empty:
     │         append ("system", build_system_message(...))     (if persona/context set)
     │         append ("user",   build_round_1_user(...))
     │     elif round_num == 2:
     │         append ("user",   build_round_2_user(...))
     │     else:  # round_num >= 3
     │         append ("user",   build_round_n_user(...))
     │
     │     raw = await port.ask(conv)
     │
     │     ConvergencePolicy.parse   ──▶ (cleaned, agreed)
     │     QuestionParser.parse      ──▶ (cleaned2, questions)
     │     TurnValidator.validate    ──▶ OK | Violation
     │             │
     │             ├─ OK → cleanup → append ("assistant", raw) → Turn
     │             │
     │             └─ Violation:
     │                   append ("assistant", raw)
     │                   append ("user", build_retry_reminder(reason))
     │                   raw2 = await port.ask(conv)
     │                   re-parse, accept, cleanup
     │                   append ("assistant", raw2) → Turn
     │
     ├─ assemble Round
     ├─ persist Debate (rounds + turns; conversations stay in memory)
     └─ publish RoundCompleted
```

## Error handling

- **Adapter errors** (timeouts, 5xx, auth failures, CLI missing, etc.): unchanged. Surface as `TurnFailed` + error `Turn` with `ElderError.kind` populated.
- **Contract violations** (shape wrong): single retry with sharpened prompt. Second reply accepted whether or not it satisfies the validator. If the second reply is still malformed, the turn is built best-effort (whatever was parsed) and a `logging.warning` is emitted with the elder id, round, and violation detail. No user-surfaced error.
- **Retry that itself fails adapter-level** (timeout, 5xx on retry): flows through the existing exception path → `TurnFailed`. The user sees the same error as if the first attempt had thrown.

## Testing

| Layer | What | File |
|---|---|---|
| Unit | `PromptBuilder.build_system_message`: persona + shared context; empty string when neither set. | `tests/unit/test_prompting.py` |
| Unit | `PromptBuilder.build_round_1_user`: question + "initial take" instruction; no CONVERGED, no QUESTIONS, no "other advisors" section. | `tests/unit/test_prompting.py` |
| Unit | `PromptBuilder.build_round_2_user`: other-advisors + user-messages sections + "exactly one question" instruction; no CONVERGED; no persona (that's in system). | `tests/unit/test_prompting.py` |
| Unit | `PromptBuilder.build_round_n_user` (n=3, n=5): other-advisors + user-messages + directed-questions + peer-questions + conditional-convergence instruction; **no "your previous answer" section**. | `tests/unit/test_prompting.py` |
| Unit | `PromptBuilder.build_retry_reminder`: contains violation reason + restated contract. | `tests/unit/test_prompting.py` |
| Unit | `TurnValidator`: full matrix — R1 OK/tag/questions, R2 OK/0Qs/2Qs/self, R3+ OK/missing-tag/yes+Q/no+0Qs/no+2Qs. | `tests/unit/test_validation.py` (new) |
| Unit | `flatten_conversation` helper: correct SYSTEM/USER/ASSISTANT tagging, separators, omits SYSTEM when absent. | `tests/unit/test_flatten_conversation.py` (new) |
| Unit | `DebateService.run_round` conversation growth: after R1, conv = [system, user_r1, assistant_r1]; after R2, adds [user_r2, assistant_r2]; after R3, adds [user_r3, assistant_r3]. | `tests/unit/test_debate_service.py` |
| Unit | `DebateService.run_round` retry path: first reply violates → retry called once → second reply valid → Turn built with second reply's data; conv has [..., assistant_bad, user_retry, assistant_good]. | `tests/unit/test_debate_service.py` |
| Unit | `DebateService.run_round` retry ceiling: second reply still invalid → Turn built best-effort, no third call. | `tests/unit/test_debate_service.py` |
| Unit | R3 full convergence: `debate.rounds[-1].converged()` returns True only when all three turns have `agreed=True`. | `tests/unit/test_debate_service.py` |
| Unit | `OpenRouterAdapter.ask(conversation)`: correct messages-array shape in POST body; system role preserved; cost accounting unchanged. | `tests/unit/test_openrouter_adapter.py` (extend) |
| Unit | `ClaudeCodeAdapter.ask(conversation)`: conversation flattened correctly before CLI invocation. | `tests/unit/test_claude_code_adapter.py` (extend) |
| Contract | `ElderPort` contract updated — `ask(conversation: list[Message]) -> str`. All adapters re-verified. | `tests/contract/test_elder_port_contract.py` |
| E2E | TUI full debate: R1+R2 auto-chain, user presses `c` for R3, scripted replies produce 2×`CONVERGED: no + Q` + 1×`CONVERGED: yes`, then R4 all yes → synthesiser-pick prompt appears. | `tests/e2e/test_tui_full_debate.py` |
| E2E | TUI elder questions: R2 always carries questions; pane rendering unchanged. | `tests/e2e/test_tui_elder_questions.py` |
| E2E | Headless: R1+R2 auto-chain; `--max-rounds` caps the loop; early termination on full convergence. | `tests/e2e/test_headless_flow.py` |

## Docs

- **`README.md`** — rewrite the "Participating in the debate" section. Describe the three phases in one short paragraph each. Update the keybindings table: `c` description becomes "Continue another round (available after R2 and while elders have not all converged)."
- **`docs/USAGE.md`** — new section "How the debate mechanic works" covering:
  - The three-phase model and why it exists (the consensus-too-fast problem).
  - The convergence contract ("yes" is "I'd not change my view"; "no" must probe).
  - The retry behaviour (one sharpened retry per contract violation).
  - The auto-synthesise-on-full-convergence behaviour.
  - How user messages and elder-to-elder questions interact with phases.

## Open risks

- **Retry cost.** One extra API call per violating elder per round. In practice, we expect most rounds to produce zero violations on the first try with well-crafted prompts; worst-case is 3 violations × 1 retry = 3 extra calls per round. Bounded and acceptable.
- **Stubborn models.** If a specific model consistently fails the contract on both attempts, the turn silently degrades to best-effort. Logged, not user-surfaced. This is the right tradeoff — we don't block the round — but worth monitoring in practice.
- **R1 "initial take" quality.** Round 1 prompts instruct elders not to converge and not to question. Some models may interpret "initial take" as short/hedging rather than a full answer. Mitigation: the prompt explicitly says "Give your initial take" — no wording discouraging depth. If we see thin R1s in practice, revise the wording.
- **Auto-synthesis UX.** When all three converge in R5, popping the synthesiser-pick modal might feel abrupt. Mitigation: keep it gated on user acceptance — the modal appears but the debate doesn't synthesise until the user confirms. User can still dismiss and press `c` to force another round.

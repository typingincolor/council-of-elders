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
- Preserve existing user capabilities: between-rounds message injection, `c`/`s`/`a`/`o` keybindings, pack personas, OpenRouter and CLI transport parity.
- Keep the domain core stateless-per-call; phase information is derived from `round.number`.

## Non-goals

- Changing the elder-count model (still three: claude/gemini/chatgpt). The "arbitrary models" brainstorm is a separate spec.
- Streaming, branching, forking debates.
- Variable retry budgets — one retry per violation, no more.
- Migrating existing saved debates' transcripts to the new contract. They remain as-is; only new turns are validated.
- Changing synthesis prompting or the synthesiser-picker UX.

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

## Components

### `council/domain/prompting.py` — split `build()` into phase-explicit methods

The current single `build()` method is replaced by four:

- **`build_round_1(debate, elder)`** — header + `Question: <prompt>` + `"Give your initial take. Do not tag convergence or ask questions — this is a silent initial round."`
- **`build_round_2(debate, elder)`** — header + question + "Other advisors said:" block + user-messages section + `"You must end with:\n\nQUESTIONS:\n@<target> <your question>\n\n— exactly one question, directed at @claude, @gemini, or @chatgpt (not yourself). Do not emit a CONVERGED tag; this is not yet a convergence round."`
- **`build_round_n(debate, elder, round_num)`** (n ≥ 3) — header + question + own-previous + other-advisors + user-messages + directed-questions + other-peer-questions + `"You may revise your answer or stand by it. End with exactly one of:\n\n(a) CONVERGED: yes — if you would not change your position after everything said.\n\n(b) CONVERGED: no, followed immediately by:\n    QUESTIONS:\n    @<target> <your probe>\n\nIf you emit CONVERGED: no you must ask exactly one question of one peer."`
- **`build_retry(original_prompt, violation_reason)`** — prepends a short "Your previous reply did not follow the required format: <reason>. Re-send your answer with the correct structure." to the original prompt. Used only by `DebateService` when a turn violates its phase contract.

Old constants `_QUESTIONS_INSTRUCTION` and `_CONVERGED_INSTRUCTION` are deleted. Each phase has its own explicit instruction string; shared helpers (`_header`, `_own_previous_answer`, `_other_advisors_section`, `_user_messages_section`, `_directed_questions_section`, `_other_questions_section`) are retained.

`build_synthesis` is unchanged.

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

### `council/domain/debate_service.py` — retry branch in `run_round`

`DebateService` gains one dependency: `validator: TurnValidator = TurnValidator()`.

Per-elder loop (inside the existing `_ask` task):

```
1. prompt = prompt_builder.build_round_<phase>(debate, elder, round_num)
2. raw = await port.ask(prompt)
3. cleaned, agreed = convergence.parse(raw)
4. cleaned2, questions = question_parser.parse(cleaned, from_elder=elder, round_number=round_num)
5. result = validator.validate(agreed=agreed, questions=questions, round_num=round_num, from_elder=elder)
6. if isinstance(result, Violation):
       retry_prompt = prompt_builder.build_retry(prompt, result.detail)
       raw2 = await port.ask(retry_prompt)
       cleaned, agreed = convergence.parse(raw2)
       cleaned2, questions = question_parser.parse(cleaned, from_elder=elder, round_number=round_num)
       # Accept whatever comes back. Do NOT re-validate-and-retry; one retry ceiling.
       # If the validator would still flag it, log a warning and proceed.
7. Apply phase-specific "drop with warn" cleanup:
       - R1: discard `agreed` and `questions` (set agreed=None, questions=())
       - R3+ with agreed=True: discard `questions` (set to ())
8. Build Turn(answer=ElderAnswer(..., agreed=agreed, text=cleaned2, ...), questions=questions)
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

### Persistence

No schema changes. `agreed=None` already round-trips via `JsonFileStore`. `Turn.questions` shape is unchanged. Old saved debates continue to deserialise.

## Data flow for a single round

```
run_round(debate)
     │
     ├─ per elder (asyncio.gather):
     │     build prompt by phase  ◀── PromptBuilder.build_round_<phase>
     │     ask(prompt) ────────── ▶ raw
     │     ConvergencePolicy.parse ──▶ (cleaned, agreed)
     │     QuestionParser.parse ─────▶ (cleaned2, questions)
     │     TurnValidator.validate  ──▶ OK | Violation
     │             │
     │             ├─ OK → cleanup → Turn
     │             │
     │             └─ Violation:
     │                   PromptBuilder.build_retry ──▶ retry_prompt
     │                   ask(retry_prompt) ──▶ raw2
     │                   re-parse, accept, cleanup → Turn
     │
     ├─ assemble Round
     ├─ persist
     └─ publish RoundCompleted
```

## Error handling

- **Adapter errors** (timeouts, 5xx, auth failures, CLI missing, etc.): unchanged. Surface as `TurnFailed` + error `Turn` with `ElderError.kind` populated.
- **Contract violations** (shape wrong): single retry with sharpened prompt. Second reply accepted whether or not it satisfies the validator. If the second reply is still malformed, the turn is built best-effort (whatever was parsed) and a `logging.warning` is emitted with the elder id, round, and violation detail. No user-surfaced error.
- **Retry that itself fails adapter-level** (timeout, 5xx on retry): flows through the existing exception path → `TurnFailed`. The user sees the same error as if the first attempt had thrown.

## Testing

| Layer | What | File |
|---|---|---|
| Unit | `PromptBuilder.build_round_1`: no CONVERGED, no QUESTIONS instruction, no "other advisors" section. | `tests/unit/test_prompting.py` |
| Unit | `PromptBuilder.build_round_2`: QUESTIONS instruction present, "exactly one" language, no CONVERGED instruction. | `tests/unit/test_prompting.py` |
| Unit | `PromptBuilder.build_round_n` (n=3, n=5): both instructions, conditional wording for yes vs no. | `tests/unit/test_prompting.py` |
| Unit | `PromptBuilder.build_retry`: prepends violation context, keeps original body. | `tests/unit/test_prompting.py` |
| Unit | `TurnValidator`: full matrix — R1 OK/tag/questions, R2 OK/0Qs/2Qs/self, R3+ OK/missing-tag/yes+Q/no+0Qs/no+2Qs. | `tests/unit/test_validation.py` (new) |
| Unit | `DebateService.run_round` retry path: first reply violates → retry called once → second reply valid → Turn built with second reply's data. | `tests/unit/test_debate_service.py` |
| Unit | `DebateService.run_round` retry ceiling: second reply still invalid → Turn built best-effort, no third call. | `tests/unit/test_debate_service.py` |
| Unit | R3 full convergence: `debate.rounds[-1].converged()` returns True only when all three turns have `agreed=True`. | `tests/unit/test_debate_service.py` |
| Contract | `ElderPort` contract unchanged. Existing contract tests still pass. | `tests/contract/test_elder_port_contract.py` |
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

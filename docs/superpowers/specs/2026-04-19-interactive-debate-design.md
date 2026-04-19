# Interactive Debate — Design

**Date:** 2026-04-19
**Status:** Approved (user skipped review gate)
**Extends:** `2026-04-19-tui-tab-view-design.md`

## Problem

The v2 TUI renders a live per-elder debate well, but the user is passive after the initial prompt. Two capabilities are missing:

1. **User-as-elder.** The user needs to take part in the conversation — ask follow-up questions, clarify the original prompt, push back on an elder's framing. Right now you fire a prompt, watch it run, and accept whatever comes out.
2. **Elder-to-elder questions.** Elders can currently *see* each other's answers in round 2+, but they can't explicitly pose questions at each other. Making the questions first-class makes the debate visibly a debate and gives the target elder an obligation to respond.

Both features inject new non-answer messages into the debate history: "here's some context from the asker" and "here's a question from one advisor to another." They share the same plumbing (extend the prompt, extend each elder's pane, extend serialisation) so they're one spec.

## Non-goals

- Streaming tokens (still v3+).
- Branching or forking a debate.
- Multi-user or remote participation — single local user.
- Voice/audio input.
- Rich-text or attachments on user messages — plain text only.

## Product decisions

| Decision | Choice |
|---|---|
| Scope | Both features, one spec. User-as-elder is the primary driver. Elder-to-elder questions use the same injection plumbing. |
| User injection timing | Between rounds only. The TextArea is re-enabled when a round completes (`awaiting_decision = True`) and disabled during a round. |
| Input widget | Replace single-line `Input` with Textual's `TextArea`. Default 3-line height, grows with content, caps at ~8 lines before scrolling. Applies to the initial prompt *and* between-round messages. |
| Submit key | `Ctrl+Enter` (macOS and Linux). Plain `Enter` inserts a newline. This matches the pattern the user already knows from Claude Code / ChatGPT's web UI. |
| Prompt structure for user messages | After "Other advisors said:" in round 2+ prompts, insert a `You (the asker) said:` section with every prior user message in chronological order, tagged with the round they followed. |
| Prompt structure for elder questions | Same chronological section, formatted as `[Gemini to Claude]: "…"` with explicit origin and target. |
| Target-elder emphasis | In round N+1, each elder also gets a prepended `Questions directed at you from the previous round:` section listing any `@<this_elder>` questions, so the target can't miss them. |
| In-pane rendering | User messages and elder-directed questions are interleaved in *every* elder's pane at their chronological position. The user sees "did Claude actually address my follow-up?" per pane. |
| Elder question signalling | Structured trailing block in the elder's raw reply: `QUESTIONS:` line followed by one or more `@elder text` lines. Parsed and stripped by a new `QuestionParser`, in parallel to the existing `ConvergencePolicy`. |
| Pane for user messages | No dedicated pane. User messages appear inline in each elder's pane (cross-cutting context). |
| Status tags | User messages have no tag. Elder questions are rendered as a distinct sub-line in both the asker's and target's panes. |

## Architecture fit

Additive domain changes, one new event, extended prompt builder, a new parser. Adapter layer gains one method on `DebateService`. TUI swaps Input → TextArea and extends pane rendering. Ports and vendor adapters don't change.

```
council/domain/
  models.py          + UserMessage value object
                     + ElderQuestion value object
                     ~ Debate.user_messages: list[UserMessage]
                     ~ Turn.questions: list[ElderQuestion]
  events.py          + UserMessageReceived(message)
  questions.py       + QuestionParser (NEW)
                     (parallel to convergence.py — strip structured tail)
  prompting.py       ~ PromptBuilder gains:
                         - "You (the asker) said:" section
                         - "Questions directed at you:" section
                         - "[<from> to <to>]" formatting for peer questions
  debate_service.py  ~ run_round now parses questions after convergence
                     + add_user_message(debate, text) method
                     + emits UserMessageReceived

council/adapters/
  storage/json_file.py  ~ serialise/deserialise UserMessage + ElderQuestion

council/app/tui/
  app.py             ~ TextArea replaces Input; Ctrl+Enter submits
                     ~ Input.Submitted handler renamed for TextArea
                     ~ Handles UserMessageReceived by dispatching to all panes
  elder_pane.py      ~ ElderPaneWidget.on_user_message(msg) → append inline
                     ~ on_turn_completed also walks turn.questions, renders
                       them inline (both asker's and target's panes)
  stream.py          ~ format_event gains branches for UserMessageReceived
                       and for rendering peer questions as Rich markup
```

## Domain model additions

```python
# council/domain/models.py (additions)

@dataclass(frozen=True)
class UserMessage:
    text: str
    after_round: int     # 0 means "before round 1" (won't normally happen —
                         # the initial prompt is not a UserMessage; it's
                         # Debate.prompt. Values >=1 map to "after round N".)
    created_at: datetime


@dataclass(frozen=True)
class ElderQuestion:
    from_elder: ElderId
    to_elder: ElderId
    text: str
    round_number: int    # the round the question was asked DURING


# Extensions to existing classes
@dataclass
class Debate:
    # ... existing fields ...
    user_messages: list[UserMessage] = field(default_factory=list)

@dataclass(frozen=True)
class Turn:
    elder: ElderId
    answer: ElderAnswer
    questions: tuple[ElderQuestion, ...] = ()   # empty if the elder didn't
                                                # emit any structured @-tags
```

`Turn.questions` is a tuple (hashable + frozen-friendly). `Debate.user_messages` is a mutable list because the aggregate grows over its lifetime.

## New domain service: QuestionParser

```python
# council/domain/questions.py

_TAG_LINE_RE = re.compile(r"^\s*@(claude|gemini|chatgpt)\s+(.+)$", re.IGNORECASE)
_HEADER_RE  = re.compile(r"^\s*QUESTIONS\s*:\s*$", re.IGNORECASE)


class QuestionParser:
    def parse(
        self,
        raw: str,
        *,
        from_elder: ElderId,
        round_number: int,
    ) -> tuple[str, tuple[ElderQuestion, ...]]:
        """Extract a trailing QUESTIONS: block.

        Expected shape, anywhere at the TAIL of the reply:

            QUESTIONS:
            @gemini Have you considered the timeline impact?
            @chatgpt What's your view on the growth tradeoff?

        Returns (cleaned_text, questions). If no valid block is found,
        returns (raw, ()).
        """
```

Parsing rules:
- Look for the last `QUESTIONS:` header line in the reply.
- If found, read subsequent lines matching `@elder text`. Stop at the first blank line or non-matching line.
- Drop an elder's own self-directed question (`@claude` from claude) — we ignore these as noise.
- Strip the entire block (header + all `@elder` lines) from the returned cleaned text.
- If no header or no valid `@elder` lines follow it, return `(raw, ())`.

Runs AFTER `ConvergencePolicy` in `DebateService`, because the `CONVERGED:` tag is always the last non-blank line. Order: strip CONVERGED → strip QUESTIONS → whatever's left is the visible answer.

## Prompt builder extensions

Round 2+ prompt, before any changes:
```
<persona>

<shared context>

Question: <original prompt>

Your previous answer:
<text>

Other advisors said:
[Claude] <text>
[Gemini] <text>

You may revise your answer if their arguments change your view, or stand by it.

End your reply with exactly one of:
CONVERGED: yes
CONVERGED: no
```

Round 2+ prompt, after changes:
```
<persona>

<shared context>

Question: <original prompt>

Your previous answer:
<text>

Other advisors said:
[Claude] <text>
[Gemini] <text>

You (the asker) said:
After round 1: "Can you focus on timeline aspect?"
After round 2: "Also please account for weekend freeze."

Questions directed at you from the previous round:
- From Claude: "Have you considered the timeline impact?"

Other questions raised between advisors:
- [ChatGPT to Gemini]: "What's your view on the growth tradeoff?"

You may revise your answer if their arguments change your view, or stand by it.

If you have questions for another advisor, include them at the end as:

QUESTIONS:
@gemini ...
@chatgpt ...

End your reply with exactly one of:
CONVERGED: yes
CONVERGED: no
```

Sections are omitted when empty (no user messages, no peer questions). "Questions directed at you" lists only questions `@this_elder` received in the preceding round, because those demand a direct answer. "Other questions raised between advisors" lists the rest so the target elder is aware of the full cross-talk but without pressure to respond.

## DebateService additions

```python
# council/domain/debate_service.py (additions)

async def add_user_message(self, debate: Debate, text: str) -> UserMessage:
    """Record a user message between rounds.

    after_round is computed as len(debate.rounds) — so if the user types
    after round 2 finishes, the message is stamped after_round=2.
    """
    msg = UserMessage(
        text=text.strip(),
        after_round=len(debate.rounds),
        created_at=self.clock.now(),
    )
    debate.user_messages.append(msg)
    self.store.save(debate)
    await self.bus.publish(UserMessageReceived(message=msg))
    return msg

# run_round extended:
# after ConvergencePolicy.parse(raw), call:
cleaned_no_questions, questions = self.question_parser.parse(
    cleaned_text,
    from_elder=elder_id,
    round_number=round_num,
)
# then pass questions into Turn construction:
return Turn(elder=elder_id, answer=ElderAnswer(..., text=cleaned_no_questions, ...),
            questions=questions)
```

## Events

```python
# council/domain/events.py (addition)

@dataclass(frozen=True)
class UserMessageReceived:
    message: UserMessage

# Added to the DebateEvent union.
```

## TUI changes

### Input → TextArea

- `council/app/tui/app.py` replaces `Input` with `TextArea`.
- `TextArea`'s key handler intercepts `ctrl+enter` to submit; plain `enter` inserts a newline (TextArea default).
- CSS caps height: `#input { max-height: 8; min-height: 3; dock: bottom; }`.
- Disabled state still works — TextArea has `disabled` reactive just like Input.
- Placeholder text: initially "Ask the council…", then "Anything to add? (Ctrl+Enter to send, or just press a shortcut)" between rounds.

### Bus consumer extension

In `CouncilApp._consume_events`:
```python
elif isinstance(ev, UserMessageReceived):
    for pane_key in ("claude", "gemini", "chatgpt"):
        self._view.pane(pane_key).on_user_message(ev.message)
```

Synthesis pane is skipped — synthesis happens *after* all user messages are done.

### Per-pane rendering

`ElderPaneWidget.on_user_message(message)` appends an inline line to the history log + buffer:
```
[dim][You after round N][/dim] <text>
```

When `on_turn_completed(answer, questions)` fires for a round, the widget renders:
- The answer (as today).
- Below, any peer questions the *current* elder asked this round, rendered as `[dim][To Gemini][/dim] <text>` — visible only in the asker's pane.
- In the target's pane, a corresponding `[dim][From Claude][/dim] <text>` line appears, with the answer (when it arrives) implicitly "answering" the question.

Signature change: `on_turn_completed` now accepts the questions list too (or reads from `turn.questions`). The bus handler passes `ev.answer` + a reference to the enclosing `Turn` so the widget can see both.

### Keybindings

No new global shortcuts. `Ctrl+Enter` is a TextArea-local key, not a global binding. `c`/`s`/`a`/`o`/`f`/`1`-`4` stay as today and fire only when focus is outside the TextArea.

## Data flow

```
User types in TextArea between rounds
        │
        ▼
Ctrl+Enter → TextArea.Submitted event → app._on_user_message_submitted
        │
        ▼
  DebateService.add_user_message(debate, text)
        │    ├─ append to debate.user_messages
        │    ├─ store.save(debate)
        │    └─ publish UserMessageReceived
        ▼
  Bus consumer → each elder pane renders the message inline
        │
        ▼
User presses `c`
        │
        ▼
  DebateService.run_round(debate)
        │    build prompt:
        │      - now includes "You (the asker) said:" with all user_messages
        │      - now includes "Questions directed at you:" from last round
        │    each elder replies
        │    ├─ ConvergencePolicy strips CONVERGED
        │    └─ QuestionParser strips QUESTIONS block → Turn.questions
        │
        ▼
  Bus → pane renders elder's cleaned answer + its own questions
        (asker's pane) + incoming questions in target pane
```

## Persistence

`JsonFileStore` serialiser/deserialiser extended:

```json
{
  "id": "...",
  "prompt": "...",
  "pack": {...},
  "rounds": [
    {
      "number": 1,
      "turns": [
        {
          "elder": "claude",
          "answer": {...},
          "questions": [
            {"from_elder": "claude", "to_elder": "gemini",
             "text": "...", "round_number": 1}
          ]
        }
      ]
    }
  ],
  "status": "in_progress",
  "synthesis": null,
  "user_messages": [
    {"text": "...", "after_round": 1, "created_at": "2026-04-19T..."}
  ]
}
```

Existing saved debates without `user_messages` / `questions` keys are read with `.get(..., [])` / `.get(..., ())` defaults so pre-v3 debates still load.

## Error handling

- User submits an empty message (whitespace only): silently ignored; TextArea clears.
- User submits while a round is still in flight: can't — TextArea is disabled. No queueing.
- Elder emits a malformed `QUESTIONS:` block (e.g. missing `@`): parser tolerates and returns `()`, no error. The raw text stays in the answer (including the broken `QUESTIONS:` line). Graceful degradation.
- Elder emits `@unknown_elder`: ignored. Only `@claude` / `@gemini` / `@chatgpt` match.
- Elder emits a `@self` question (`@claude` from Claude): dropped silently. Avoids weird self-directed prompts.

Domain services still never raise for adapter failures — unchanged contract.

## Testing strategy

| Layer | What | Test file |
|---|---|---|
| Unit | `UserMessage`, `ElderQuestion` dataclass construction + equality | `tests/unit/test_models.py` (add cases) |
| Unit | `QuestionParser.parse` — well-formed block, missing header, unknown elder, self-directed, trailing whitespace, no block | `tests/unit/test_question_parser.py` |
| Unit | `PromptBuilder` — "You said" section present when user_messages populated, "Questions directed at you" present when target had questions last round, sections omitted when empty | `tests/unit/test_prompting.py` (extend) |
| Unit | `DebateService.add_user_message` appends, saves, publishes, returns the message with the right `after_round` | `tests/unit/test_debate_service.py` (extend) |
| Unit | `DebateService.run_round` populates `Turn.questions` from the reply | `tests/unit/test_debate_service.py` (extend) |
| Unit | `JsonFileStore` round-trips `user_messages` and per-turn `questions` | `tests/unit/test_json_file_store.py` (extend) |
| E2E | TUI: user types a message between rounds → appears in all three elder panes; next round prompt includes it | `tests/e2e/test_tui_user_messages.py` |
| E2E | TUI: elder emits a `QUESTIONS: @gemini ...` block → question appears in Claude's pane as `[To Gemini]` and Gemini's pane as `[From Claude]`; Gemini's round 2 prompt includes "Questions directed at you" | `tests/e2e/test_tui_elder_questions.py` |
| Edited E2E | Existing full-debate e2e — change `Input` references to `TextArea`, `pilot.press` becomes `pilot.press(..., "ctrl+enter")` | `tests/e2e/test_tui_full_debate.py` |

## What's explicitly out of scope

- User can't edit or delete a sent message. (If important, defer to v4.)
- User can't target a specific elder (e.g., "@claude only"). All user messages are moderator-level, shown to all three.
- Elders can't ask questions of the *user* (one-way only: users→elders and elders→elders). If they want clarification, they can use dissent or flag it in their answer text.
- No hotkey to "ask for a user response" — elders have no way to pause and demand input.
- Synthesis prompt ignores elder questions. The synthesiser sees the full history as today; the tension captured by questions is embedded in the answers themselves.

## Open questions deferred to implementation

- Textual's `TextArea` submit API: does it natively support `ctrl+enter` via `bindings`, or do we need a custom `on_key` handler? Verify at implementation time.
- Should the "Anything to add?" placeholder change as the debate progresses (e.g. to "Clarify further, or press c for another round")? Start simple, adjust if it feels stale.

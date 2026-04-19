# TUI Tab View Redesign — Design

**Date:** 2026-04-19
**Status:** Approved (pending implementation plan)
**Supersedes:** Chronological-stream layout from `2026-04-18-council-of-elders-design.md`

## Problem

The v1 TUI renders all debate activity into a single chronological stream. Real-world use exposed four pain points:

1. **Interleaving.** All three elders write into the same pane, so a single elder's answer is fragmented across other elders' lines, making each individual voice hard to read.
2. **Scrolling loss.** Long answers push earlier content off the top before the user has finished reading.
3. **Comparison.** Putting two elders' takes side by side requires scrolling back and forth.
4. **Post-debate review.** After synthesis, finding "what did Gemini say in round 1?" means hunting through the scrollback.

A tab-per-elder layout (plus a synthesis tab) solves 1, 2, and 4 by giving each elder a self-contained pane. Comparison (3) is addressed by rendering three panes side by side when the terminal is wide enough.

## Non-goals

- Changes to the domain core, ports, adapters, `DebateService`, event model, or persistence. None change.
- Token streaming from vendor CLIs. Still v2 scope.
- Abandon/override e2e tests. Still open from the earlier review list; not addressed here.
- Resume / debate history browser. Still v2 scope.

## Product decisions

| Decision | Choice |
|---|---|
| Default layout | Three columns side-by-side when terminal width ≥ 240 cols; tabs below that. |
| Breakpoint rationale | Each elder gets ≥ 80 characters of readable width. 80 is the classic code wrap width; narrower columns produce unpleasant paragraph wrap. |
| User override | `f` toggles between auto / forced-tabs / forced-columns. Forced mode disables the auto-switch until cleared. |
| Navigation | Number keys `1`/`2`/`3`/`4` jump directly to Claude/Gemini/ChatGPT/Synthesis. `Tab` / `Shift+Tab` cycles through them. Both bindings coexist. |
| In-pane content | Each elder pane shows the full round history (round 1, divider, round 2, …) scrollable within the pane. |
| Synthesis view | A dedicated 4th tab/pane. Always present in tabbed mode (placeholder before first synthesis). In 3-col mode, the synthesis pane is hidden until the user presses `s` and picks an elder; once in-flight it expands to full width (collapsing the 3-col view behind it) and stays full-width afterwards. |
| Thinking UX | Live elapsed-seconds counter + rotating whimsical verb. E.g. `Claude · Pondering… 12s`. Verb is picked once per turn and stays stable for that turn. |
| Verb pool | Shared across elders. Twelve verbs: Pondering, Deliberating, Ruminating, Mulling, Reflecting, Brewing, Cogitating, Meditating, Musing, Noodling, Pontificating, Contemplating. |
| Tab label states | `Claude · Pondering… 12s` (thinking) / `Claude ✓` (converged) / `Claude ↻` (dissenting) / `Claude ⚠` (error). |
| Global keybindings | `c` / `s` / `a` / `o` unchanged. Operate on the debate, not the focused pane. |

## Architecture fit

The redesign is entirely a primary-adapter change. Specifically: `council/app/tui/`. The domain core, ports, driven adapters, event model, and `DebateService` don't change.

```
council/app/tui/
  app.py              # (rewritten) CouncilApp — plumbing: bus consumer,
                      # keybindings, layout switcher ownership
  stream.py           # (unchanged) format_event — still the per-message renderer
  elder_pane.py       # (new) ElderPane widget — one elder's round history,
                      # thinking-line with live verb + elapsed counter
  council_view.py     # (new) CouncilView widget — holds 4 ElderPanes,
                      # switches between 3-col and tabbed layouts reactively
```

`format_event` stays as the per-message Rich-markup formatter. `ElderPane` uses it to render each completed turn. Keeping the formatter decoupled from layout means stream-widget tests don't change.

## Widget responsibilities

### `ElderPane`

One elder's debate history, plus its current thinking state.

- Holds a `RichLog` for past rounds (appended to via `format_event`) and a `ThinkingLine` for the current in-flight turn.
- Exposes `label_text` as a `reactive` string — the string shown on the owning tab or at the top of the column.
- Methods called from the outside: `on_turn_started(round_number, elder_id)`, `on_turn_completed(answer)`, `on_turn_failed(error)`.
- Owns a small set of ticker tasks (same `_tasks` set + done-callback pattern as `CouncilApp._spawn`).
- Synthesis mode (`synthesis=True` init arg): no verb rotation, label becomes `Synthesis` / `Synthesising… 12s` / `Synthesis ✓`; content is a single answer, no round dividers, placeholder text before first completion. Thinking-ticker is driven by `on_turn_started` just like any other pane — `CouncilApp` calls it when the user confirms a synthesiser in the modal, since the bus doesn't emit a dedicated `SynthesisStarted` event.

### `CouncilView`

Composite layout widget. Holds the four `ElderPane` instances. Decides whether to render them inside a `TabbedContent` or a `Horizontal` based on terminal width and user override state.

- Constant `MIN_WIDTH_PER_ELDER = 80`, threshold `MIN_WIDTH_3COL = 3 * 80 = 240` (allowance for dividers absorbed into column padding).
- `_pick_layout(width: int, forced: Literal["tabs","columns"] | None) -> Literal["tabs","columns"]` — pure function, unit-tested in isolation.
- `on_resize` hook re-evaluates layout. If the decision flips, the view re-composes; `ElderPane` instances are re-parented, preserving their state.
- `f` keybinding toggles `forced_mode`: `None` → `"tabs"` → `"columns"` → `None`. Status indicator in the footer reflects the current mode.

### `CouncilApp`

- Owns the `InMemoryBus`, `DebateService`, the four `ElderPane` instances, the `CouncilView`, and the persistent `Input`.
- `_consume_events` is the single subscriber; it dispatches events to the right pane by `event.elder`.
- Keybindings `c` / `s` / `a` / `o` / `f` / `1`-`4` / `Tab` / `Shift+Tab` are attached here.
- System-level notices (unhealthy elders at startup, "No elders available") render in a small banner area above the `CouncilView`, visible in all layouts.

## Event flow

```
DebateService publishes → InMemoryBus
        │
        ▼
CouncilApp._consume_events
        │
        ├─ TurnStarted(elder)       → panes[elder].on_turn_started(round_num)
        │                             (roll verb, start ticker, update label)
        │
        ├─ TurnCompleted(elder, a)  → panes[elder].on_turn_completed(a)
        │                             (cancel ticker, append to history, label ✓/↻)
        │
        ├─ TurnFailed(elder, err)   → panes[elder].on_turn_failed(err)
        │                             (cancel ticker, append error turn, label ⚠)
        │
        ├─ RoundCompleted(r)        → awaiting_decision = True
        │                             (no pane mutation)
        │
        └─ SynthesisCompleted(a)    → panes["synthesis"].on_turn_completed(a)
                                      + focus synthesis pane
                                      + is_finished = True
```

## Ticker and verb mechanics

Verbs are chosen by a `VerbChooser` callable:

```python
# council/app/tui/elder_pane.py
class VerbChooser(Protocol):
    def __call__(self) -> str: ...

_VERB_POOL: tuple[str, ...] = (
    "Pondering", "Deliberating", "Ruminating", "Mulling",
    "Reflecting", "Brewing", "Cogitating", "Meditating",
    "Musing", "Noodling", "Pontificating", "Contemplating",
)

class RandomVerbChooser:
    def __call__(self) -> str:
        return random.choice(_VERB_POOL)

class FixedVerbChooser:
    def __init__(self, verb: str) -> None:
        self._verb = verb
    def __call__(self) -> str:
        return self._verb
```

`ElderPane` takes `verb_chooser: VerbChooser` and `clock: Clock` as init args (defaults to `RandomVerbChooser()` and `SystemClock()`). Tests inject `FixedVerbChooser("Pondering")` + `FakeClock` for deterministic output.

The ticker is a background task that loops `await asyncio.sleep(1)` and re-renders the label with the elapsed seconds. Cancelled on `on_turn_completed` / `on_turn_failed` / `on_unmount`.

## Responsive layout

```python
# council/app/tui/council_view.py
MIN_WIDTH_PER_ELDER = 80
MIN_WIDTH_3COL = 3 * MIN_WIDTH_PER_ELDER  # 240

def _pick_layout(
    width: int,
    forced: Literal["tabs", "columns"] | None,
) -> Literal["tabs", "columns"]:
    if forced is not None:
        return forced
    return "columns" if width >= MIN_WIDTH_3COL else "tabs"
```

`CouncilView.on_resize` calls `_pick_layout(self.size.width, self._forced_mode)`. If the returned layout differs from the currently-mounted one, the view unmounts the old container and mounts the new one with the same four `ElderPane` instances. Pane state (history, label, ticker tasks) is preserved because state lives on the panes, not the container.

Default terminal on a 13-15" laptop full-screen is ~120-180 cols — below the threshold, so most laptop users see tabs. External monitors and ultra-wide setups get three columns. `f` overrides either way.

## Error handling

Unchanged from v1. `TurnFailed` events render via `format_event` into the elder's round history; the tab label shows `⚠` for that round and reverts to `✓`/`↻` when the next round succeeds.

Startup health-check banner from the existing `_run_health_checks` persists — it surfaces above `CouncilView` in a notices area rather than in the (now absent) chronological stream.

## Testing strategy

Existing tests stay green. Light edits only where they touched the chronological stream.

| Layer | What | Test file |
|---|---|---|
| Unit | `_pick_layout` returns the right mode given width + forced arg | `tests/unit/test_layout_threshold.py` |
| Unit | `ElderPane.label_text` transitions (thinking → converged/dissenting/error) using `FixedVerbChooser` + `FakeClock` | `tests/unit/test_elder_pane_labels.py` |
| Unit | `RandomVerbChooser` returns a verb from the pool (monkeypatch `random.choice`) | `tests/unit/test_verb_chooser.py` |
| E2E | Number keys `1`/`2`/`3`/`4` and `Tab` change focused pane | `tests/e2e/test_tui_tab_navigation.py` |
| E2E | Two-round debate shows round 1 and round 2 in each pane with a divider | `tests/e2e/test_tui_history_per_elder.py` |
| E2E | Resize via `pilot.resize_terminal` flips the layout; `f` forces an override | `tests/e2e/test_tui_layout_mode_toggle.py` |
| Edited E2E | Existing full-debate test asserts per-pane content instead of a flat stream | `tests/e2e/test_tui_full_debate.py` |
| Edited E2E | Health-check test still asserts via `rendered_lines` (the `_write_notice` helper keeps appending there for test observability); only the visual location of the notices changes | `tests/e2e/test_tui_health_check_gate.py` |

Helper `_pane_lines(app, elder_id) -> list[str]` added to `tests/e2e/conftest.py` to keep per-pane assertions clean.

Visual fidelity (exact markup, pixel layout) is not asserted. We test semantic content and key transitions.

## What's explicitly out of scope

- Token streaming.
- Per-elder verb pools / vendor-specific voice.
- Branching debates or resume.
- Multiple synthesis attempts within one debate (`s` after a prior synthesis is a no-op currently; stays that way).
- Dissent-count-based banner or "how divergent is this round?" summary — valuable but deferred.

## Open questions deferred to implementation

- Exact `TabbedContent` vs `Horizontal` wiring in Textual — API ergonomics verified at implementation time, design doesn't over-commit.
- Whether `pilot.resize_terminal` covers enough of the responsive contract or we need to exercise the resize handler directly in unit tests. Start with the former, fall back to the latter if flaky.

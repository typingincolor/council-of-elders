# Council of Elders — Design

**Date:** 2026-04-18
**Status:** Approved (pending implementation plan)

## Purpose

A terminal-based tool that sends a prompt to three LLM vendors simultaneously — Claude, Gemini, and ChatGPT — collects their answers, runs a multi-round debate where each elder can see and revise in light of the others, and produces a single synthesized answer chosen by the user.

**Hard constraint:** must not incur Anthropic/Google/OpenAI API charges. The orchestrator uses each vendor's subscription-backed CLI (Claude Code, Gemini CLI, Codex CLI), running under the user's existing paid plans.

## Non-goals

- Managing vendor authentication. The user runs each vendor's `login` command once; the orchestrator shells out and trusts the CLI is authenticated.
- Supporting models beyond the three listed. Adding a fourth elder is a future change, not a v1 concern.
- Running in CI or on servers. This is a local, interactive developer tool.
- Cost tracking. Usage counts against the user's subscription quotas which the vendors already surface.

## Product decisions

| Decision | Choice |
|---|---|
| Interaction model | Interactive Textual TUI with a chat loop |
| Collaboration flow | Convergence-based debate, user-controlled: after each round the user decides continue / synthesize now / abandon, and picks which elder synthesizes |
| Layout | Single chronological stream, each message color-coded and labeled `[Claude]` / `[Gemini]` / `[ChatGPT]` / `[Synthesis]` |
| Stack | Python 3.12+, Textual for TUI, pytest for tests, `asyncio` for concurrency |
| Context input | Council packs: a directory at `~/.council/packs/<name>/` containing an optional `shared.md` (applied to all elders) plus optional per-elder overrides `claude.md` / `gemini.md` / `chatgpt.md` |
| Architecture | Hexagonal (ports & adapters) |
| Methodology | TDD |

## Architecture

Pure domain core with driving adapters on one side (how the user drives it) and driven adapters on the other (how the core reaches the outside world).

```
                 ┌───────────────────────┐
   Driving       │   Textual TUI (app)   │   ← primary adapter
   adapters      │   + Headless CLI      │   ← primary adapter (scripting/tests)
                 └──────────┬────────────┘
                            │ calls
                 ┌──────────▼────────────┐
                 │       DOMAIN CORE     │  pure, no I/O, fully unit-tested
                 │                       │
                 │  • Debate (aggregate) │
                 │  • Round, Turn,       │
                 │    ElderAnswer,       │
                 │    ElderError         │
                 │  • CouncilPack        │
                 │  • PromptBuilder      │
                 │  • ConvergencePolicy  │
                 │  • DebateService      │
                 │                       │
                 │  depends only on ports│
                 └──────────┬────────────┘
                            │ implements
              ┌─────────────┼─────────────┬───────────────┐
              │             │             │               │
   Driven  ┌──▼───┐     ┌───▼───┐     ┌───▼────┐     ┌────▼─────┐
   ports   │Elder │     │Trans. │     │ Clock  │     │EventBus  │
           │Port  │     │Store  │     │        │     │          │
           └──┬───┘     └───┬───┘     └───┬────┘     └────┬─────┘
              │             │             │               │
   Driven  ┌──▼──────────┐ ┌▼──────────┐ ┌▼──────────┐ ┌──▼────────┐
   adapters│ClaudeCode-  │ │JsonFile-  │ │System-    │ │asyncio-   │
           │Adapter      │ │Store      │ │Clock      │ │QueueBus   │
           │GeminiCLI-   │ │In-Memory- │ │FakeClock  │ │InMemoryBus│
           │Adapter      │ │Store(test)│ │  (test)   │ │  (test)   │
           │CodexCLI-    │ │           │ │           │ │           │
           │Adapter      │ │           │ │           │ │           │
           │FakeElder    │ │           │ │           │ │           │
           │  (shipped)  │ │           │ │           │ │           │
           └─────────────┘ └───────────┘ └───────────┘ └───────────┘
```

### Invariants

- `council.domain.*` has zero imports from `textual`, `subprocess`, `asyncio.subprocess`, `pathlib`, `httpx`, or any adapter module.
- Ports are `typing.Protocol` classes in `council/domain/ports.py`.
- Adapters depend on the core; the core never imports from adapters.
- `FakeElder`, `InMemoryStore`, `FakeClock` are **shipped** in the package (not test-only), because integration tests, e2e tests, and demo scripts all reuse them.

### Package layout

```
council/
  domain/
    models.py          # Debate, Round, Turn, ElderAnswer, ElderError, CouncilPack
    events.py          # DebateEvent union: TurnStarted/Completed/Failed, RoundCompleted, ...
    ports.py           # ElderPort, TranscriptStore, Clock, CouncilPackLoader, EventBus
    prompting.py       # PromptBuilder
    convergence.py     # ConvergencePolicy
    debate_service.py  # DebateService (application service, still pure)
  adapters/
    elders/
      claude_code.py   # ClaudeCodeAdapter: shells out to `claude -p`
      gemini_cli.py    # GeminiCLIAdapter: shells out to `gemini -p`
      codex_cli.py     # CodexCLIAdapter: shells out to `codex exec`
      fake.py          # FakeElder: scripted responses for tests + demos
    storage/
      json_file.py     # JsonFileStore: ~/.council/debates/<id>.json
      in_memory.py     # InMemoryStore: test double
    packs/
      filesystem.py    # FilesystemPackLoader: reads ~/.council/packs/<name>/
    bus/
      asyncio_queue.py # AsyncioQueueBus
      in_memory.py     # InMemoryBus: test double
    clock/
      system.py
      fake.py
  app/
    tui/               # Textual app (primary adapter)
      app.py
      widgets/
    headless/          # non-TUI entrypoint, useful for scripting + e2e tests
      main.py
  tests/
    unit/              # pure core tests, fastest
    contract/          # every ElderPort impl passes the same suite
    integration/       # real CLI smoke tests, skipped in CI
    e2e/               # Textual pilot + FakeElder, full flow
```

## Domain model

```python
ElderId = Literal["claude", "gemini", "chatgpt"]

@dataclass(frozen=True)
class ElderError:
    elder: ElderId
    kind: Literal["timeout", "cli_missing", "auth_failed", "nonzero_exit", "unparseable"]
    detail: str

@dataclass(frozen=True)
class ElderAnswer:
    elder: ElderId
    text: str | None           # None iff error is set
    error: ElderError | None
    agreed: bool | None        # convergence signal; None = undeclared or unparseable
    created_at: datetime

@dataclass(frozen=True)
class Turn:
    elder: ElderId
    answer: ElderAnswer

@dataclass
class Round:
    number: int
    turns: list[Turn]          # one per elder; partial if some errored

    def converged(self) -> bool:
        return len(self.turns) == 3 and all(t.answer.agreed is True for t in self.turns)

@dataclass
class CouncilPack:
    name: str
    shared_context: str | None
    personas: dict[ElderId, str]   # missing key = no persona override

@dataclass
class Debate:
    id: str
    prompt: str
    pack: CouncilPack
    rounds: list[Round]
    status: Literal["in_progress", "synthesized", "abandoned"]
    synthesis: ElderAnswer | None
```

### Domain services (also pure)

```python
class PromptBuilder:
    def build(self, debate: Debate, elder: ElderId, round_num: int) -> str: ...
    def build_synthesis(self, debate: Debate, by: ElderId) -> str: ...

class ConvergencePolicy:
    def parse(self, raw: str) -> tuple[str, bool | None]:
        """Strip trailing 'CONVERGED: yes|no' line; return (cleaned_text, agreed)."""

class DebateService:
    def __init__(
        self,
        elders: dict[ElderId, ElderPort],
        store: TranscriptStore,
        clock: Clock,
        bus: EventBus,
    ): ...
    async def run_round(self, debate: Debate) -> Round: ...
    async def synthesize(self, debate: Debate, by: ElderId) -> ElderAnswer: ...
```

### Prompt shape

**Round 1:**
```
<persona (per-elder persona if set, else empty)>
<shared_context (if set)>

Question: <debate.prompt>

Answer the question. End your reply with exactly one of:
CONVERGED: yes
CONVERGED: no

(Use CONVERGED: yes only if you would not change your answer after seeing what other advisors say.)
```

**Round 2+:** same header, plus:
```
Your previous answer:
<debate.rounds[-2].turn_for(this_elder).answer.text>

Other advisors said:
[Claude] <...>
[Gemini] <...>
[ChatGPT] <...>

You may revise your answer if their arguments change your view, or stand by it. End with CONVERGED: yes|no.
```

**Synthesis:** the chosen elder receives persona + shared context + original question + every round's answers + "produce the final synthesized answer; no CONVERGED tag."

## Ports

```python
class ElderPort(Protocol):
    elder_id: ElderId
    async def ask(self, prompt: str, *, timeout_s: float = 120) -> str: ...
    async def health_check(self) -> bool: ...

class TranscriptStore(Protocol):
    def save(self, debate: Debate) -> None: ...
    def load(self, debate_id: str) -> Debate: ...

class Clock(Protocol):
    def now(self) -> datetime: ...

class CouncilPackLoader(Protocol):
    def load(self, pack_name_or_path: str) -> CouncilPack: ...

# DebateEvent is a discriminated union defined in domain/events.py:
#   TurnStarted(elder) | TurnCompleted(elder, answer) | TurnFailed(elder, error)
#   | RoundCompleted(round) | SynthesisCompleted(answer) | DebateAbandoned

class EventBus(Protocol):
    async def publish(self, event: DebateEvent) -> None: ...
    def subscribe(self) -> AsyncIterator[DebateEvent]: ...
```

`ElderPort.ask` is deliberately flat: take a prompt, return reply text. Vendor-specific flag wrangling lives in the adapter. The domain never knows which vendor it's talking to.

## Data flow (one debate)

```
User types prompt in TUI
        │
        ▼
App creates Debate(id, prompt, pack)              ← CouncilPackLoader.load("chief-of-staff")
        │
        ▼
DebateService.run_round(debate)                   ← ROUND 1
  ├─ PromptBuilder.build(debate, claude, 1)   ─┐
  ├─ PromptBuilder.build(debate, gemini, 1)   ─┤ asyncio.gather
  └─ PromptBuilder.build(debate, chatgpt, 1)  ─┘
        │
        ▼
  Each ElderPort.ask() runs concurrently; bus emits:
    TurnStarted(elder) → TurnCompleted(elder, answer) or TurnFailed(elder, err)
        │
        ▼
  ConvergencePolicy.parse() on each reply → agreed flag
  Round appended to Debate; TranscriptStore.save(debate)
        │
        ▼
App emits RoundCompleted; TUI renders each answer into the stream
        │
        ▼
    ┌─── User decision prompt ────┐
    │ [c] continue (another round)│
    │ [s] synthesize now          │
    │ [a] abandon                 │
    │ [o] override convergence    │
    └──────────────┬──────────────┘
                   │
        ┌──────────┼──────────────────────────┐
        ▼          ▼                          ▼
  run_round(2)  synthesize(by=<elder>)   mark abandoned
                     │
                     ▼
             Chosen elder receives full history;
             returns synthesized answer
                     │
                     ▼
             debate.synthesis = ElderAnswer(...)
             debate.status = "synthesized"
             TUI renders [Synthesis] block, stream ends
```

**Concurrency:** three elders run in parallel via `asyncio.gather`. TUI streams `TurnStarted` / `TurnCompleted` events so answers appear in the order they arrive, not the order they were launched.

## Error handling

Errors are domain values, not exceptions that escape the core:

- **Timeout** (default 120s/elder, configurable via env/CLI): cancel the subprocess, record `ElderError(kind="timeout")`. The round still completes with whichever elders replied.
- **CLI missing** (not on `$PATH`): detected at app startup via `health_check()`. App prints a setup hint naming the missing binary and refuses to start unless at least one elder is healthy.
- **Auth failure**: vendor CLIs have distinctive exit codes / stderr. Adapter maps them to `kind="auth_failed"` with a hint like "run `claude login`".
- **Nonzero exit, other**: `kind="nonzero_exit"`, `detail` captures stderr tail.
- **Unparseable response** (missing `CONVERGED:` tag): keep the text, set `agreed = None`; TUI shows a subtle marker; user can use `[o] override convergence` to proceed.

Domain services **never raise** for adapter failures — they return `Round` objects containing error turns. The TUI is the only layer that decides how to surface errors to the human.

## Council packs

Directory at `~/.council/packs/<name>/`:

```
~/.council/packs/chief-of-staff/
  shared.md        # applied to all three elders (optional)
  claude.md        # overrides just for Claude (optional)
  gemini.md        # overrides just for Gemini (optional)
  chatgpt.md       # overrides just for ChatGPT (optional)
```

Selected via `council --pack chief-of-staff` (or an in-TUI pack picker). All files optional; a pack with only `shared.md` gives every elder the same role, which is the common case.

`FilesystemPackLoader` reads the directory, returns a `CouncilPack`. Unknown filenames are ignored (not an error) to leave room for future expansion.

## Persistence

Debates are written to `~/.council/debates/<debate_id>.json` after every round. `JsonFileStore.list_recent()` powers a debate-history view (future, not v1).

v1 does not support resuming an abandoned debate — once closed, it's archive-only.

## Testing strategy

| Layer | What it tests | How |
|---|---|---|
| **Unit** (`tests/unit/`) | Domain models, `PromptBuilder`, `ConvergencePolicy`, `DebateService` | Pure Python, `FakeElder` + `InMemoryStore` + `FakeClock`. ~80% of the suite. |
| **Contract** (`tests/contract/`) | Every `ElderPort` impl satisfies the protocol | Parametrized; `FakeElder` always runs, real adapters gated behind `@pytest.mark.integration`. |
| **Integration** (`tests/integration/`) | Real CLIs work when installed and authed | Skipped in CI; `pytest -m integration` locally. One smoke test per elder. |
| **E2E** (`tests/e2e/`) | Full debate through the TUI | `textual.pilot.Pilot` drives the app; elders are `FakeElder` with scripted replies. Asserts stream renders `[Claude]`/`[Gemini]`/`[ChatGPT]`/`[Synthesis]` in correct order. |

### TDD order

Implement units in this order, red/green/refactor for each:

1. Domain models (`Debate`, `Round`, `ElderAnswer`, `CouncilPack`)
2. `ConvergencePolicy`
3. `PromptBuilder`
4. `DebateService` (using `FakeElder`, `InMemoryStore`, `FakeClock`)
5. `FilesystemPackLoader`
6. `JsonFileStore`
7. `ClaudeCodeAdapter` → write contract test first, then implementation
8. `GeminiCLIAdapter` → same
9. `CodexCLIAdapter` → same
10. Headless CLI entrypoint
11. Textual TUI (widgets tested via `textual.pilot`)

## Open questions for implementation planning

- Exact command-line flags for each vendor CLI's non-interactive mode (`claude -p`? `--print`? JSON vs text output?) — verify at implementation time, don't design around assumptions.
- Whether to stream tokens from each CLI or wait for the full reply. v1: wait for full reply (simpler, keeps chronological stream readable). Streaming is a v2 consideration.
- Default timeout per elder. Start at 120s; surface as `COUNCIL_TIMEOUT` env var.

## What's explicitly out of v1 scope

- Debate resume / branching
- More than three elders
- Token streaming from vendor CLIs
- A debate-history browser TUI
- Cost / quota display
- Remote packs (everything is local filesystem)

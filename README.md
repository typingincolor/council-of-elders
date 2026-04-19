# Council of Elders

![Three elders debate around a wooden table, each with a glowing coloured tablet, a central synthesised answer between them.](docs/banner.png)

[![CI](https://github.com/typingincolor/council-of-elders/actions/workflows/ci.yml/badge.svg)](https://github.com/typingincolor/council-of-elders/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Send one prompt to Claude, Gemini, and ChatGPT simultaneously, watch them debate, and get one synthesised answer. Use your existing paid vendor subscriptions by default, or route through OpenRouter with a single API key.

> **Full user guide:** [`docs/USAGE.md`](docs/USAGE.md) — covers what the tool is for, how the debate mechanic works, writing council packs, model selection, troubleshooting, and how to get real value from it.

## Quick start

```bash
# One-time setup
uv venv && source .venv/bin/activate
uv pip install -e .

# Make sure each vendor CLI is installed and logged in
claude -p "hi"
gemini -p "hi"
codex exec "hi"

# Run the TUI
council

# Or one-shot, no UI
council-headless "Your question here."
```

If Gemini hits quota (common on AI Pro), set once:

```bash
export COUNCIL_GEMINI_MODEL=gemini-2.5-flash
```

### Using OpenRouter

If you'd rather not install all three vendor CLIs, put an OpenRouter key in `~/.council/config.toml`:

```toml
[openrouter]
api_key = "sk-or-v1-..."

[openrouter.models]
claude = "anthropic/claude-sonnet-4.5"
gemini = "meta-llama/llama-3.1-70b-instruct"
chatgpt = "openai/gpt-5"
```

Or export `OPENROUTER_API_KEY` in your shell (wins over the TOML file).

When a key is resolvable, all three elders go through OpenRouter and the vendor CLIs are not touched. After each round the TUI shows `[openrouter] round: $X · session: $X · credits remaining: $X`. Headless mode prints the equivalent line once after synthesis.

If no key is set, the council falls back to the existing vendor-CLI behaviour with no change.

### How the debate unfolds

The council runs a structured three-phase debate so the elders actually engage rather than producing three parallel monologues:

**Round 1 — Silent initial answers.** Each elder answers your question independently, without seeing the others. No convergence, no cross-talk.

**Round 2 — Cross-examination (auto-runs after round 1).** Each elder now sees the other two's round-1 answers and must ask exactly one question of one peer (`@claude`, `@gemini`, or `@chatgpt`). Convergence is still not possible — this is the dialogue step.

**Round 3 and beyond — Open debate.** Each elder either says `CONVERGED: yes` (they'd not change their view even hearing everything the others said) or `CONVERGED: no` and asks exactly one further question of a peer. You press `c` to trigger each round. When all three elders converge in the same round, you're prompted to pick a synthesiser automatically.

Converged elders stay in the conversation. If a peer directs a question at an elder after it already converged, it sees that question in its next turn and may hold its position or change its mind.

Each elder maintains a real multi-turn conversation with memory across rounds, so they reason over their own prior answers natively.

Between rounds, the input at the bottom is re-enabled. Type a clarifying question or comment and press **Enter** to send it to the elders — they'll see it in the next round's prompt. Use **Ctrl+Enter** to insert a newline if you want to write a longer, multi-line message.

Elder questions are signalled with a trailing block:

```
QUESTIONS:
@gemini Have you considered the timeline impact?
```

The question appears labelled `[To Gemini]` in the asker's pane and `[From Claude]` in the target's pane, and the target gets a "Questions directed at you" section in its next prompt.

## Keybindings during a debate

| Key | Action |
|---|---|
| `c` | Continue another round (available after round 2, while elders haven't all converged) |
| `s` | Synthesise — pick who writes the final answer |
| `a` | Abandon |
| `o` | Override convergence |
| `1` / `2` / `3` / `4` | Jump to Claude / Gemini / ChatGPT / Synthesis pane |
| `Tab` / `Shift+Tab` | Cycle forward / backward through panes |
| `f` | Toggle layout: auto → force tabs → force columns → auto |

The layout automatically uses three columns when the terminal is at least 240 characters wide (80 per elder) and tabs otherwise. Press `f` to override.

## Council packs

Create `~/.council/packs/<name>/` with any of `shared.md`, `claude.md`, `gemini.md`, `chatgpt.md` — the contents are injected as persona/context for each elder. See the [usage guide](docs/USAGE.md) for examples.

```bash
council --pack chief-of-staff
```

## Model selection

```bash
council --claude-model sonnet --gemini-model gemini-2.5-flash --codex-model gpt-5-codex
```

Or via env vars: `COUNCIL_CLAUDE_MODEL`, `COUNCIL_GEMINI_MODEL`, `COUNCIL_CODEX_MODEL`.

## Testing

```bash
pytest                        # unit + e2e (fast)
pytest -m integration         # also hits real CLIs (requires auth)
```

## Requirements

- Python 3.12+
- Claude Code CLI (`claude`) — `claude login`
- Gemini CLI (`gemini`) — `gemini auth login`
- Codex CLI (`codex`) — `codex login`

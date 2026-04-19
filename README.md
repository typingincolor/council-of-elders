# Council of Elders

![Three elders debate around a wooden table, each with a glowing coloured tablet, a central synthesised answer between them.](docs/banner.png)

[![CI](https://github.com/typingincolor/council-of-elders/actions/workflows/ci.yml/badge.svg)](https://github.com/typingincolor/council-of-elders/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Send one prompt to Claude, Gemini, and ChatGPT simultaneously, watch them debate, and get one synthesised answer, all using your existing paid subscriptions (no API charges).

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

### Participating in the debate

Between rounds, the input at the bottom is re-enabled. Type a clarifying question or comment and press **Enter** to send it to the elders — they'll see it in the next round's prompt. Use **Ctrl+Enter** to insert a newline if you want to write a longer, multi-line message.

Elders can also pose questions to each other by ending their reply with a block like:

```
QUESTIONS:
@gemini Have you considered the timeline impact?
@chatgpt What about the growth tradeoff?
```

When that happens, the question appears labelled `[To Gemini]` in the asker's pane and `[From Claude]` in the target's pane, and the target gets a "Questions directed at you" section in its next prompt.

## Keybindings during a debate

| Key | Action |
|---|---|
| `c` | Continue another round — elders see each other's answers |
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

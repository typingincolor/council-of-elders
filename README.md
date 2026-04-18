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

## Keybindings during a debate

| Key | Action |
|---|---|
| `c` | Continue another round — elders see each other's answers |
| `s` | Synthesise — pick who writes the final answer |
| `a` | Abandon |
| `o` | Override convergence |

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

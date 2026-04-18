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

### Choosing models per elder

Each vendor's CLI supports a `--model` flag; the council forwards one per elder:

```bash
council --gemini-model gemini-2.5-flash --codex-model gpt-5-codex
```

Or set environment variables once and forget:

```bash
export COUNCIL_CLAUDE_MODEL=sonnet
export COUNCIL_GEMINI_MODEL=gemini-2.5-flash
export COUNCIL_CODEX_MODEL=gpt-5-codex
```

**Heads-up:** Gemini Pro has a very tight free/Pro quota under the `gemini` CLI. Use `gemini-2.5-flash` for the Gemini slot if you hit `quota_exhausted` errors — Flash has ~10× the quota.

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

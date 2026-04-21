# Council of Elders

![Three elders debate around a wooden table, each with a glowing coloured tablet, a central synthesised answer between them.](docs/banner.png)

[![CI](https://github.com/typingincolor/council-of-elders/actions/workflows/ci.yml/badge.svg)](https://github.com/typingincolor/council-of-elders/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> ## ⚠️ This is an experiment, not a finished product.
>
> The premise was "three diverse LLMs debate, then synthesise a better answer than any one of them alone". After four experiments (and one scoring bug I initially missed), the actual story is more specific than that:
>
> - **Model diversity matters.** A roster of three distinct providers (Anthropic + Meta + OpenAI) produces synthesis preferred ~44% of the time over the strongest individual answer, at n=8. A homogeneous same-model roster drops that to ~31%.
> - **Personas don't substitute, and compose *negatively*.** Adding per-elder personas to a same-model roster is neutral. Adding them on top of the diverse roster drops preference by ~0.13. Persona context overhead is the likely cause; the roles pack is **not** recommended.
> - **The debate rounds are net-negative on synthesis quality.** Running R1 only, then synthesising — with no cross-examination rounds between elders — beats the full three-round debate by ~0.13 on judged preference. R2 cross-exam is the damage site; R3+ adds nothing more. The tool's current default pipeline (R1 + R2 + R3 + synthesis) is not the best configuration it can produce.
> - **Format interventions tested — no format beats R1-only.** Replacing R2 cross-exam with a *silent-revise* R2 (elders privately re-write their own answer after reading peers, no convergence/questions pressure) and a free-form synthesis prompt were both tested against the R1-only baseline at n=16 per cell. Silent-revise was a wash (Δ = +0.031, inside noise); the free-form synthesis prompt consistently tripped the "don't describe the debate" guardrail. The debate-rounds bottleneck isn't about *how* elders engage in R2 — it's that engaging at all is the damage site.
> - **Best-R1 is a genuine baseline.** The strongest individual R1 beats synthesis in roughly half of debates even in the best configuration. If you're only going to keep one output, keep it. But synthesis wins 5–6 times out of 32 in good configurations, and ties another third, so it's not dominated. A multi-judge "pick the best of three R1s" output is also roughly equivalent to synthesis (rate 0.562 vs 0.5 break-even at n=16, within noise) — and the two preference judges only agree on which R1 is best 56% of the time, so "best" isn't a well-defined target for about half the prompts.
>
> The working configuration is **three distinct providers, bare pack, R1-only synthesis** — which the current code doesn't directly support as a mode. Adding it is a small change and tracked in the results docs below.
>
> **Caveat:** all experiments used *automated* model-to-model debate. Human-in-the-loop multi-model consultation (a human picking which thread to pull, rephrasing, directing follow-ups) wasn't tested and may well behave differently.
>
> Full methodology and per-debate results: [`docs/experiments/`](docs/experiments/). Key reads:
> - [`2026-04-19-9288-homogenisation.md`](docs/experiments/2026-04-19-9288-homogenisation.md) — first probe; showed homogeneous councils underperform.
> - [`2026-04-20-judge-replication.md`](docs/experiments/2026-04-20-judge-replication.md) — judge-family bias in the original scoring. Directional findings survive.
> - [`2026-04-20-f294-results.md`](docs/experiments/2026-04-20-f294-results.md) — 2×2 model × role experiment. Cell C (diff model, bare pack) wins.
> - [`2026-04-20-226f-results.md`](docs/experiments/2026-04-20-226f-results.md) — debate-depth ablation. R1-only synthesis beats full debate.
> - [`2026-04-21-f13d-format-ablation.md`](docs/experiments/2026-04-21-f13d-format-ablation.md) — silent-revise R2 tested against R1-only baseline (n=16). No help.
> - [`2026-04-21-f13d-best-of-n.md`](docs/experiments/2026-04-21-f13d-best-of-n.md) — multi-judge best-of-N vs synthesis (n=16). Roughly equivalent. Inter-judge agreement on "best" is only 56%.
>
> The code still runs. The experiments tell you where the working configuration is.
>
> ---

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

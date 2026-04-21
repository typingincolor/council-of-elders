# Council of Elders — User Guide

## What this tool is for

Council of Elders sends one question to three large language models — Claude, Gemini, and ChatGPT — at the same time, lets them read each other's answers, revise their thinking, and then produces one synthesised answer you can use.

The point is not to pick a winner. The point is to get the **blind-spot coverage** that a single model cannot give you. Each model has different training data, different biases, and a different house style. When all three agree, the answer is usually trustworthy. When they disagree, the disagreement itself is the valuable information — it tells you the question has more than one reasonable answer and you should think harder before committing.

You stay in the driver's seat throughout. The tool does not decide when the debate is "done" and it does not hide the raw answers from you. It just makes the mechanical parts — fan-out, coordination, synthesis — feel seamless.

### Why it is not a chatbot

Most AI tools give you one voice and a long transcript. This one gives you three voices and a structured process:

- One shot, three independent takes, in parallel.
- Optional further rounds where each model sees the others' answers and can revise.
- A final synthesis step where one model (chosen by you) reads everything and produces a single consolidated answer.

Use it when a question is important enough to want more than one opinion — strategy, decisions, drafts you need to get right, sensitive communications, trade-off analysis.

### Why it uses your existing subscriptions

The tool shells out to the three vendors' official CLI tools (`claude`, `gemini`, `codex`). Each of those CLIs is billed against your existing paid plan. There are no API keys, no per-token charges, and no traffic routed through a third party. Your prompts and replies never leave your machine except via the vendor CLIs you already trust.

## Requirements

- **Python 3.12 or newer** (check with `python3 --version`).
- **Claude Code CLI** (`claude`) — install, then `claude login` once.
- **Gemini CLI** (`gemini`) — install, then `gemini auth login` once.
- **Codex CLI** (`codex`) — install, then `codex login` once.
- **A terminal that supports rich text** (any modern macOS, Linux, or Windows terminal works).

Confirm each vendor is authenticated by running it standalone once:

```bash
claude -p "say hi"
gemini -p "say hi"
codex exec "say hi"
```

If any of those fail, fix that first. Council of Elders is a thin coordinator; it cannot log in for you.

## Installing

From the project directory:

```bash
uv venv                  # or: python3 -m venv .venv
source .venv/bin/activate
uv pip install -e .      # or: pip install -e .
```

This puts two commands on your `PATH` (inside the venv):

- `council` — the interactive TUI.
- `council-headless` — one-shot mode, prints answers and synthesis to stdout and exits.

## Daily use

### Interactive mode (the TUI)

```bash
source .venv/bin/activate
council
```

You'll see an empty chronological stream at the top and a prompt box at the bottom. Type your question, hit Enter.

**Round 1** runs immediately — each elder answers independently, without seeing the others.

**Round 2** runs automatically straight after R1. Now each elder has seen the other two's R1 answers and must ask exactly one question of exactly one peer. This is where real dialogue starts: no convergence is possible yet; the point is to surface disagreement.

Once R2 completes, the tool pauses for your decision.

As each elder returns, its answer appears in the stream with a label and (in R3+) a status tag:

- **`(converged)`** — green — "I stand by this answer even after seeing what the others say."
- **`(dissenting)`** — yellow — "I still have questions, and here's my probe."
- **No tag** — R1 and R2 have no CONVERGED tag by design.

### What to do between rounds

| Key | Action | Use it when |
|---|---|---|
| `c` | **Continue** — run another round. In R3+, each elder must say CONVERGED: yes or probe further with a question. | The debate still has open tension, or you want to test durability of the agreement. Only available after R2. |
| `s` | **Synthesise** — brings up a modal. Press `1`/`2`/`3` to pick who writes the final answer. | You have enough material. |
| `a` | **Abandon** — closes the debate, saves the transcript, exits. | You realise the question is wrong, or you want to start over. |
| `o` | **Override** — treats all three turns of the most recent round as converged. | The elders are stuck and you want to force synthesis without another round. |

When all three elders emit `CONVERGED: yes` in the same round, the synthesiser-pick modal opens automatically — no need to press `s`. You can still dismiss it and press `c` to force another round, or `s` at any earlier point.

Press `Ctrl+C` at any time to quit.

### Headless mode

Same flow, no UI. Always runs R1+R2 (the opening exchange), continues to R3+ until convergence or `--max-rounds`, synthesises, prints everything, exits:

```bash
council-headless "Your question here."
council-headless --max-rounds 6 "A deeper question."
council-headless --pack chief-of-staff --synthesizer gemini "Your question."
```

The `--max-rounds` flag caps total rounds (including R1+R2). Default is 3 — enough for the opening exchange plus one R3 if elders don't converge immediately. Minimum value is 2.

Useful for scripting, piping into other tools, or when you just want the output and don't need to steer the debate.

### How the debate mechanic works

The council runs a three-phase debate — a deliberate shape designed to avoid the "three parallel monologues, everyone claims consensus" failure mode that plagues naive multi-model setups.

**Phase 1 — Silent initial answers (Round 1).** Each elder sees only the question (and any persona/pack context). No knowledge of the others. No convergence tag. No questions yet. The point: capture each elder's unfiltered first take.

**Phase 2 — Cross-examination (Round 2, auto-chains after R1).** Each elder now sees the other two's R1 answers. Every elder MUST end with exactly one question targeted at exactly one peer (`@claude`, `@gemini`, or `@chatgpt`). Convergence is not yet possible — this phase's only job is to make dialogue happen. Without this step, models tend to declare "I agree" on their own answers before ever engaging.

**Phase 3 — Open debate with convergence (Round 3+).** Now each elder must either:
- `CONVERGED: yes` — "I would not change my view after everything that has been said"; or
- `CONVERGED: no` + a new `QUESTIONS:` block with one further probe.

No middle ground. If an elder has nothing more to probe, convergence is the honest signal. If they're still probing, they must point at *what* they're still uncertain about.

**Convergence can be un-made.** An elder that converged in round N can be pulled back in if a peer directs a question at it in round N+1. It either reaffirms `CONVERGED: yes` (implicitly answering the question, or addressing it in prose) or flips to `CONVERGED: no` and probes further. Convergence is not a one-way valve.

**Retries.** If an elder's reply doesn't follow the phase contract (e.g. R2 with no question, or R3+ with CONVERGED: no but no question), the tool silently re-asks once with a sharpened reminder. Second reply is accepted whatever comes back — the debate proceeds rather than blocking on a stubborn model.

**Conversation memory.** Each elder maintains a real multi-turn conversation across rounds. The elder sees its own prior answers as assistant turns in its history, not as paraphrases pasted into the user message. Prompts stay shorter each round, and OpenRouter prompt caching kicks in for free.

**Between-round user messages.** You can type a clarifying question or nudge at any point after R2 completes. Your message gets injected into each elder's next user turn as a "You (the asker) said:" section. Elders see it alongside the other peers' answers and the directed-questions section.

## Council packs — giving each elder a persona

A "council pack" is a folder at `~/.council/packs/<name>/` that contains Markdown files loaded into the prompt sent to each elder. This is how you turn the council into *your* chief of staff, *your* legal advisor, *your* design review panel, or any other role you care to stand up.

### Pack files

| File | Who gets it | Use it for |
|---|---|---|
| `shared.md` | All three elders | A role, persona, or standing context that applies to every advisor. |
| `claude.md` | Only Claude | Per-elder persona override. |
| `gemini.md` | Only Gemini | Per-elder persona override. |
| `chatgpt.md` | Only ChatGPT | Per-elder persona override. |

All files are optional. A pack with only `shared.md` is the common case.

### Example: a simple pack

```
~/.council/packs/chief-of-staff/
  shared.md           # "You are my Chief of Staff. Help me think clearly and..."
```

Use it:

```bash
council --pack chief-of-staff
```

### Example: a diverse panel

```
~/.council/packs/product-review/
  shared.md           # "Review this product decision for a mid-stage startup..."
  claude.md           # "You are the head of engineering. Weight technical risk heavily."
  gemini.md           # "You are the head of design. Weight user experience heavily."
  chatgpt.md          # "You are the head of growth. Weight adoption dynamics heavily."
```

Use it:

```bash
council --pack product-review
```

This turns the council into a three-way internal panel where each voice has a distinct lens. Ideal for decisions with cross-functional trade-offs.

### Writing good pack instructions

Treat `shared.md` like a system prompt for a well-run team. Cover:

- **Who they are to you** — role, relationship, expected voice.
- **What they should focus on** — speed, quality, risk, clarity, something else.
- **How they should push back** — challenge assumptions, point out missing context, suggest alternatives.
- **How they should write** — tone, length, formatting preferences, words to avoid.

The more concrete you are, the more coherent the council's output. Vague personas produce vague answers. A well-written pack can transform the tool from "three models in a trench coat" to "a real advisory team."

## Model selection

Each vendor CLI lets you pick which specific model to use. Council of Elders forwards this through:

```bash
council --claude-model sonnet --gemini-model gemini-2.5-flash --codex-model gpt-5-codex
```

Or once, permanently:

```bash
export COUNCIL_CLAUDE_MODEL=sonnet
export COUNCIL_GEMINI_MODEL=gemini-2.5-flash
export COUNCIL_CODEX_MODEL=gpt-5-codex
```

### Recommended defaults

- **Gemini**: use `gemini-2.5-flash` unless you really want Pro. Pro has a very tight daily quota under Google AI Pro and you will hit `quota_exhausted` errors quickly. Flash has roughly ten times the allowance and is still a strong model.
- **Claude**: `sonnet` for most work; `opus` for hard reasoning tasks where you want the best judgement available.
- **Codex**: `gpt-5-codex` or whichever the newest flagship is at the time.

You do not have to set these — the vendors' defaults are sensible. The flags exist for when their defaults are wrong for your use.

## Transcripts

Every debate is saved to `~/.council/debates/<uuid>.json` after each round. The file contains the full prompt, pack, every turn, every error, and the final synthesis. These are for your records — there is no automatic browsing UI in the current version.

To delete them: `rm -r ~/.council/debates/`.

## Common questions

**"One elder is taking forever. What do I do?"**
Default per-elder timeout is 45 seconds. If that's too short (unusual), the CLIs will time out and the round will complete with an error turn for the slow elder. Your options: press `s` and synthesise from the two that answered, or press `c` and try again. If one vendor is reliably slow, consider switching its model to a faster variant.

**"I keep hitting `quota_exhausted` on Gemini."**
Set `COUNCIL_GEMINI_MODEL=gemini-2.5-flash`. If that also runs out, you are genuinely over quota for the day.

**"Pressing `c` does nothing."**
Focus should move off the Input widget after you submit, but if you ever see this, press `Tab` once to shift focus, then `c`.

**"The elders are all saying very similar things."**
Either the question was too narrow (no real disagreement to surface), or your pack is pushing them too hard into the same persona. Try a more open-ended question, or diversify the pack (per-elder personas instead of shared).

**"I don't want one of the elders on this question."**
Not currently supported cleanly — all three always run. If it matters, set the unwanted elder's model to a fast cheap one and ignore its output.

**"Can I rerun just one elder?"**
No. Rerun the whole round with `c`.

## What this tool is not

- **Not a chat interface.** The council answers in bursts, not in flowing conversation. If you want to chat, use one of the vendor CLIs directly.
- **Not a prompt library.** Packs are personas, not prompt templates. The question you ask is still yours to write.
- **Not a benchmark.** The council is not trying to rank the models. It's trying to use their disagreements as signal.
- **Not free infrastructure.** Usage counts against your three existing subscriptions. Keep an eye on quotas.

## Getting good value from it

- **Ask questions that benefit from multiple perspectives.** Strategic choices, drafts of sensitive messages, trade-off analysis, "should I" decisions. Don't waste the council on questions that have one right answer (maths, syntax, lookups).
- **Read all three drafts before synthesising.** The synthesis is useful, but the raw drafts often contain a line or phrase you'll want to keep verbatim. Don't skip them.
- **Pay attention to dissent.** A single `(dissenting)` elder on a prompt everyone else converged on is worth reading carefully. It's often catching something the other two missed.
- **Keep the pack tight.** Over-long packs dilute the models' attention. Two pages of clear instructions beat ten pages of vague guidance.
- **Iterate on the question.** If the first round produces three vague answers, the question was vague. Press `a`, refine, try again.

## Using OpenRouter

The council can route all three elders through [OpenRouter](https://openrouter.ai/) instead of the vendor CLIs. This is useful when you don't want to install and authenticate each vendor CLI separately, or when you're running the council in an environment (server, container) where those CLIs aren't available.

### Activation

OpenRouter mode turns on automatically when an API key is resolvable. The resolution order is:

1. `OPENROUTER_API_KEY` environment variable
2. `openrouter.api_key` in `~/.council/config.toml`

If neither source yields a non-empty string, the council uses the vendor CLIs as before.

### Config file

`~/.council/config.toml`:

```toml
[openrouter]
api_key = "sk-or-v1-..."

[openrouter.models]
ada = "anthropic/claude-sonnet-4.5"
kai = "meta-llama/llama-3.1-70b-instruct"
mei = "openai/gpt-5"
```

(Legacy keys `claude` / `gemini` / `chatgpt` still work and are mapped automatically to `ada` / `kai` / `mei`, with a deprecation warning.)

**Roster guidance.** The default ships three distinct providers (Anthropic + Meta + OpenAI) so the adaptive policy picks `full_debate` mode out of the box. This is one reasonable configuration among many — not a claim that this specific trio is best-performing. The tool's strongest evidence is **negative**: a homogeneous roster (three copies of one model, or three from one provider) reduces synthesis quality below the best individual answer, and the tool will warn you and degrade to `best_r1_only` on such rosters. The positive claim (which diverse roster is *best*) is not established — see [`docs/experiments/2026-04-20-judge-replication.md`](experiments/2026-04-20-judge-replication.md) for why the earlier-looking-best "substituted" roster turned out to be judge-family-specific. Pick three different providers; don't pick three of the same.

**Pipeline override — `--policy r1_only`.** The adaptive policy picks `full_debate` on diverse rosters, but the 2026-04 experiments found that debate rounds are net-negative on synthesis quality: R1-only-then-synthesise beats the full three-round debate by ~0.13 on judged preference. For diverse rosters, pass `--policy r1_only` to skip R2+ and synthesise directly from the three R1 answers. Distinct from `--policy best_r1_only`, which skips both the debate rounds *and* synthesis (returns one of the three R1 answers verbatim). See [`docs/experiments/2026-04-20-226f-ablation.md`](experiments/2026-04-20-226f-ablation.md) and [`docs/experiments/2026-04-21-f13d-format-ablation.md`](experiments/2026-04-21-f13d-format-ablation.md).

Tip: Gemini thinking models (e.g. `gemini-2.5-pro`, `gemini-3.1-pro-preview`) occasionally emit their whole answer into the `reasoning` field with empty `content`. The adapter falls back to `reasoning` in that case so the elder isn't silent, but the fallback text is the model's scratchpad rather than a polished reply. Prefer non-thinking models like `gemini-2.5-flash` if you want the cleanest output.

OpenRouter model ids are namespaced as `provider/model`. See [OpenRouter's model list](https://openrouter.ai/models) for what's available.

### Model precedence (per elder)

Highest wins:

1. `--claude-model` / `--gemini-model` / `--codex-model` CLI flag
2. `COUNCIL_CLAUDE_MODEL` / `COUNCIL_GEMINI_MODEL` / `COUNCIL_CODEX_MODEL` env var
3. `[openrouter.models].<elder>` in `~/.council/config.toml`
4. Hard-coded default (`anthropic/claude-sonnet-4.5`, `meta-llama/llama-3.1-70b-instruct`, `openai/gpt-5`)

Note: in OpenRouter mode the CLI flag and env var values are passed verbatim as OpenRouter model ids. A CLI-flavoured alias like `sonnet` will not resolve through OpenRouter — use the full OpenRouter id (`anthropic/claude-sonnet-4.5`) when that transport is active.

### Cost visibility

- **TUI:** after each round, a notice appears: `[openrouter] round: $X · session: $X · credits remaining: $X` (or `credits used: $X` for pay-as-you-go keys without a hard limit).
- **Headless:** a single summary line is printed after the synthesis.

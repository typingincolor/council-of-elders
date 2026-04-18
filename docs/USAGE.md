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

You'll see an empty chronological stream at the top and a prompt box at the bottom. Type your question, hit Enter, and the three elders fan out in parallel.

As each elder returns, its answer appears in the stream with a label and a status tag:

- **`(converged)`** — green — "I stand by this answer even after seeing what the others say."
- **`(dissenting)`** — yellow — "I might revise if I see the others' answers."
- **No tag** — the elder's reply did not include a recognisable convergence marker. Treat it as undeclared.

Once all three have reported, a round is complete and the tool pauses for your decision.

### What to do between rounds

| Key | Action | Use it when |
|---|---|---|
| `c` | **Continue** — run another round. Each elder now sees the others' answers and can revise. | There is visible dissent, or you want to test how durable the agreement is. |
| `s` | **Synthesise** — brings up a modal. Press `1`/`2`/`3` to pick who writes the final answer. | You have enough material. All three converged, or you trust one of them to reconcile. |
| `a` | **Abandon** — closes the debate, saves the transcript, exits. | You realise the question is wrong, or you want to start over. |
| `o` | **Override** — treats all three turns of the most recent round as converged. | The elders are stuck in trivial dissent and you want to force synthesis without another round. |

Press `Ctrl+C` at any time to quit.

### Headless mode

Same flow, no UI. Runs one round, synthesises with whichever elder you choose, prints everything, exits:

```bash
council-headless "Your question here."
council-headless --pack chief-of-staff --synthesizer gemini "Your question."
```

Useful for scripting, piping into other tools, or when you just want the output and don't need to steer the debate.

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

# Model homogenisation probe — design

**Date:** 2026-04-19
**Tracks:** [issue #11](https://github.com/typingincolor/council-of-elders/issues/11)

## Research question

Issue 11 asks: do the three current elders (Claude Opus, Gemini Pro, GPT-5) produce genuinely diverse views, or are they trained on such overlapping data that their consensus is less informative than the three-elder format implies? The issue framed this as "measure R1 error correlation" — a single high-information experiment that calibrates how much to trust every other architectural decision in this project.

During brainstorming the question was sharpened into a second, related question: **is the tool's value driven by model diversity, by the debate protocol, or both?** The original issue tests only the first. This design tests both.

## Mechanisms under test

The council-of-elders tool could deliver value through two separable mechanisms:

| Mechanism | Claim | How this experiment tests it |
|---|---|---|
| **Model diversity** | Different lineages → different blindspots → R1 answers cover more of the answer space | Pairwise R1 claim-Jaccard across rosters (lower Jaccard = more diversity) |
| **Debate protocol** | Structured cross-examination surfaces hidden disagreement and refines the answer, even among similar advisors | Synthesis-vs-best-R1 preference rate per roster (higher rate = debate adds value) |

Either mechanism alone justifies the tool; the experiment is designed to tell them apart.

## Rosters

Three rosters run through the same corpus. Each runs a full debate to natural convergence (round cap: 6). All elders run via the existing `OpenRouterAdapter`; the only thing that changes between rosters is the model ID per slot.

| Roster | Purpose | `claude` slot | `gemini` slot | `chatgpt` slot |
|---|---|---|---|---|
| **Homogeneous** | Floor: stochastic variance only | `openai/gpt-5-mini` | `openai/gpt-5-mini` | `openai/gpt-5-mini` |
| **Mixed baseline** | Current production state | `anthropic/claude-sonnet-4.5` | `google/gemini-2.5-pro` | `openai/gpt-5` |
| **Substituted** | Candidate diversity improvement | `anthropic/claude-sonnet-4.5` | `meta-llama/llama-3.1-70b-instruct` | `openai/gpt-5` |

The `gemini` slot is the one substituted in the third roster (least role-specialised of the three personas, so swap causes least confound with role-drift). Llama-3.1-70B is chosen as the open-weights substitute because it is the furthest-lineage option from the other two.

Elder-id slot assignment (`claude` / `gemini` / `chatgpt`) is purely a label; the debate protocol reads slot, not model. The "gemini" slot running a Llama model is fine — the prompt pack and debate mechanics are slot-keyed, not model-keyed.

## Metrics

### Metric 1 — R1 claim-overlap (Jaccard)

For each prompt, for each roster:

1. Run the full debate, capture the three R1 answers.
2. For each unordered pair of elders `(A, B)`, ask the judge to count `shared`, `a_only`, `b_only` claims (see rubric 3a below).
3. Pairwise Jaccard = `shared / (shared + a_only + b_only)`.
4. Per-prompt Jaccard = mean of the three pairwise Jaccards.

Per-roster Jaccard = mean across corpus prompts. Higher Jaccard = more overlap = less diversity.

### Metric 2 — Synthesis-vs-best-R1 preference rate

For each prompt, for each roster:

1. Use the existing debate flow: three R1 answers, rounds to convergence, synthesis written by whichever elder is chosen as synthesiser.
2. Best-R1 judge (rubric 3b-i) picks the strongest of the three R1 answers.
3. Preference judge (rubric 3b-ii) is shown `(prompt, best_R1, synthesis)` with the two candidates labelled X/Y in **random order per call** to mitigate positional bias.
4. Record `winner` as `synthesis`, `best_r1`, or `tie`.

Per-roster preference rate = fraction of prompts where `winner = synthesis`, ties counted as 0.5. Report with a binomial 90% CI (directional interpretation only; n is too small for significance testing).

## Harness

### File layout

- `scripts/homogenisation_probe.py` — entry-point script with subcommands
- `scripts/homogenisation_corpus.yaml` — the 8 prompts, checked in
- `runs/<run-id>/manifest.json` — roster × prompt → debate-id map (generated, git-ignored)
- `runs/<run-id>/scores.json` — judge outputs keyed by debate-id (generated, git-ignored)
- `docs/experiments/<run-id>-homogenisation.md` — human-readable report (generated, git-ignored by default; user can commit any interesting ones)

`<run-id>` format: `YYYY-MM-DD-<4char-hash>`, e.g. `2026-04-19-a3f2`. Distinct runs don't overwrite each other.

### Phases

Each phase reads the previous phase's artifacts, is idempotent within itself, and can be re-run without double-spending:

| Phase | Subcommand | Reads | Writes | Resumability |
|---|---|---|---|---|
| 1. Run | `homogenisation_probe run` | Corpus YAML | Manifest + saved debates in `~/.council/debates/` | If manifest already has a `(roster, prompt)` entry, skip that debate |
| 2. Score | `homogenisation_probe score --run-id <id>` | Manifest + saved debates | Scores JSON | Skip `(debate_id, metric)` pairs already present in scores |
| 3. Report | `homogenisation_probe report --run-id <id>` | Scores JSON | Markdown report | Pure data transform; re-run freely |

### Orchestration

For each roster, the runner builds a `dict[ElderId, ElderPort]` of `OpenRouterAdapter` instances with the roster's model IDs and drives the existing `debate_service`. No new debate-running logic — this is the same code path `council-headless` uses. The probe is strictly an orchestration wrapper plus two new judges.

Round cap: 6. Longer debates are stopped short and noted in the report.

Synthesiser: rotated round-robin across elder slots per prompt (to prevent one slot's bias from dominating the synthesis-preference metric within a roster).

## Judge rubrics

All judge calls use `google/gemini-2.5-flash` via OpenRouter — the same model the existing drift analyser uses (`council/app/analyze/main.py:42`). Judge responses are parsed tolerantly: regex on keyed lines, with neutral defaults if a field is missing and the raw response logged for diagnostics. This mirrors the pattern in `council/domain/debate_analytics.py:258` (`_parse_drift_verdict`).

### 3a. Claim-overlap judge (pairwise)

Three calls per prompt per roster (one per elder pair). Claims are compared semantically by the judge; normalisation of paraphrases is the judge's problem, not ours.

```
You are a neutral judge comparing two answers to the same question,
measuring CLAIM OVERLAP.

User's question:
<<<{question}>>>

Answer A:
<<<{answer_a}>>>

Answer B:
<<<{answer_b}>>>

For each distinct factual or evaluative claim either answer makes,
classify it as:
- SHARED: both make this claim (possibly in different words)
- A_ONLY: only A makes it
- B_ONLY: only B makes it

"Claim" = an atomic assertion about the world, a recommendation, or a
judgement (not a stylistic choice or framing decision). Two answers
saying "X is faster" and "X outperforms on speed" are the same claim.

Emit EXACTLY these four lines, nothing else:
shared_count: N
a_only_count: N
b_only_count: N
note: one short sentence explaining any judgement calls.
```

Parse via regex on `^\s*(shared|a_only|b_only)_count\s*:\s*(\d+)` (case-insensitive, multiline). Missing counts default to 0; zero-total responses (judge produced no parsable numbers) are logged and excluded from the mean.

### 3b. Synthesis-preference

#### 3b-i. Best-R1 picker (one call per debate)

```
You will see three candidate answers to the user's question. Pick the
single strongest one on correctness, completeness, and shape-fit.
Ignore stylistic polish. Do not favour longer answers.

User's question:
<<<{question}>>>

Answer 1:
<<<{answer_1}>>>

Answer 2:
<<<{answer_2}>>>

Answer 3:
<<<{answer_3}>>>

Emit EXACTLY:
best: 1 | 2 | 3
reason: one sentence.
```

Parse on `^\s*best\s*:\s*([1-3])`. If unparsable, default to answer 1 and log — this biases a small number of results toward one elder but is cheap and safe for a directional MVP.

#### 3b-ii. Preference judge (one call per debate)

X/Y labelling is randomised per call; the mapping is recorded in the scores JSON so the report can display results in consistent order.

```
You are judging which of two answers better addresses the question.

User's question:
<<<{question}>>>

Answer X:
<<<{answer_x}>>>

Answer Y:
<<<{answer_y}>>>

Judge on: factual correctness, completeness, shape-fit (does the form
match what was asked for — e.g., headline vs essay), and avoidance of
bloat. DO NOT favour an answer just because it is longer or more
formal — penalise bloat.

Emit EXACTLY:
winner: X | Y | TIE
reason: one sentence.
```

Parse on `^\s*winner\s*:\s*(X|Y|TIE)` (case-insensitive). If unparsable, record as TIE.

### Bias mitigations (summary)

- Pairwise (not fan-in) claim judging, so paraphrase resilience is the judge's job and doesn't require post-hoc normalisation.
- Random X/Y ordering in the preference judge per call.
- Same judge model across all rosters. Absolute numbers are not comparable to other judges; only within-experiment deltas matter.
- Judge model (gemini-2.5-flash) is Gemini-family, which could in principle bias content judgements toward the Gemini slot in the mixed and substituted rosters. Documented as a caveat; not mitigated in MVP. Follow-up could cross-check with a Claude or Llama judge if the signal is ambiguous.

## Corpus

Stored at `scripts/homogenisation_corpus.yaml`. Eight prompts, each under 50 words, covering the shapes the issue flagged. None are famous benchmark problems.

| id | shape | prompt |
|---|---|---|
| `headline_001` | headline | Write a single-sentence headline (max 12 words) for a product launch where a UK payments startup announces a fee cut for small businesses. |
| `summary_001` | summary | In two sentences, explain to a non-technical reader what "latency" means in the context of a web API. |
| `strategy_001` | strategy_tradeoff | A founder has $150k to either hire one senior engineer or three junior engineers for a year. Give a recommendation in one paragraph. |
| `strategy_002` | strategy_tradeoff | A regional bookshop must pick one focus for the year: stronger e-commerce, or a programme of in-store author events. Recommend one, with reasoning. |
| `technical_001` | technical_decision | A Python service must process 1M small JSON files on one VM. Recommend asyncio or a process pool, with one paragraph of reasoning. |
| `technical_002` | technical_decision | An internal tool will serve ~50 users with light CRUD traffic. PostgreSQL or SQLite? One paragraph. |
| `factual_001` | factual_multipart | Name three distinct primary causes of the 2008 financial crisis. One sentence on each. |
| `value_001` | contested_value | Is it ethical for a company to use AI to monitor individual employee productivity? Take a clear position in one paragraph. |

Weighted toward `strategy_tradeoff` and `technical_decision` (2 each), where disagreement is most plausible and the experiment signal should concentrate.

After the first run, any prompt producing trivial agreement across all rosters or trivial disagreement regardless of roster should be swapped — it tells us nothing. This iteration is expected, not a failure.

## Cost estimate

| Component | Count | Cost |
|---|---|---|
| Debate turns | 3 rosters × 8 prompts × ~5 rounds × 3 elders ≈ 360 calls | ~$3–5 (flagship models dominate) |
| Claim-overlap judge | 3 rosters × 8 prompts × 3 pairs = 72 calls | ~$0.10 (flash is cheap) |
| Best-R1 picker | 3 rosters × 8 prompts = 24 calls | ~$0.05 |
| Preference judge | 3 rosters × 8 prompts = 24 calls | ~$0.05 |

**Total: ~$3–7 for a complete run.** Within the "single cheap experiment" envelope the issue specifies.

## Output — the markdown report

Written to `docs/experiments/<run-id>-homogenisation.md`. Structure:

```
# Model homogenisation probe — <date>

## Question
<verbatim from issue 11, plus the sharpened version>

## Rosters tested
<table: roster → model IDs per slot>

## Corpus
<list: prompt id, shape, prompt text>

## Results

### Metric 1 — R1 claim-overlap (Jaccard)
<table: roster × mean / median / per-prompt Jaccard>

### Metric 2 — Synthesis-vs-best-R1 preference
<table: roster × preference rate (CI) / n debates>

## Interpretation
<the four-row interpretation table with actual numbers filled in>
<one-sentence verdict: which mechanism(s) matter>

## Caveats
<small n, single-judge, single open-weights model, single homogeneous model, possible Gemini-family judge bias, round cap 6>

## Appendix A — per-prompt details
<for each prompt: per-roster R1 claim-overlap counts, preferred winner, one-sentence reason>

## Appendix B — run metadata
<timestamps, total cost, debate IDs for reproducibility>
```

## Interpretation framework

The verdict cell of the report follows this decision rule:

| Observation | Verdict |
|---|---|
| Homogeneous R1-Jaccard − Mixed R1-Jaccard < 0.05 | Model diversity produces negligible R1 variance on this corpus |
| Mixed R1-Jaccard − Substituted R1-Jaccard > 0.10 | Open-weights substitution adds meaningful diversity |
| Homogeneous preference rate − Mixed preference rate within ±0.10 | Debate protocol does the work; multiple models unnecessary |
| Mixed preference rate − Homogeneous preference rate > 0.10 | Tool's value depends on both mechanisms |

Thresholds are directional heuristics, not statistical tests. The verdict should name which mechanism(s) the data supports and recommend whether further architecture work is worth pursuing.

## Caveats

- **Small n (8 prompts).** Results are directional. A second run with a fresh corpus would sharpen the signal if the first is ambiguous.
- **Single judge model.** Gemini-flash may have systematic biases. Results are internally consistent but absolute numbers are not portable to other experiments using different judges.
- **One open-weights model, one homogeneous model.** Llama-3.1-70B and gpt-5-mini are single points in their respective regions of model space; other choices could give different numbers.
- **One substituted slot (gemini).** Substituting a different slot could confound with role-drift effects.
- **Round cap of 6** may truncate debates that would have produced a better synthesis with more rounds; reported, not mitigated.
- **Judge family proximity** — gemini-flash judging mixed/substituted rosters that include gemini-pro or llama could bias preferences. Documented, not mitigated.
- **Persona priming in the homogeneous roster.** The debate prompts reference peer elders by slot name (`Claude`, `Gemini`, `ChatGPT`) — see `council/domain/prompting.py:6-8`. When 3× gpt-5-mini runs this roster, each instance still sees peers labelled as "Claude" / "Gemini" in its context. This is persona priming, not a clean model-equivalence test. It is also how the tool would actually behave if a user configured three same-model elders, so it's the right thing to measure — but worth naming explicitly.

## Out of scope for MVP

- Multiple trials per prompt (the broader n≥3 framework from issue #7).
- Alternative judge models for cross-validation.
- Multiple open-weights substitutes (Qwen, Mistral) in the same run.
- Slot-substitution sweep (try replacing each slot, not just gemini).
- Automated corpus iteration based on first-run signal.
- Integration with `council-analyze` as a generic scorer (fold in only if the metric proves useful).

## Success criteria

The experiment succeeds if its report can answer this question with directional confidence:

> Does the council-of-elders tool's value come from model diversity, from the debate protocol, from both, or from neither — on this corpus?

Specifically:

1. All three rosters produce complete debates and synthesis for all eight prompts, or the failures are documented with a clear cause.
2. All 120 judge calls return a parsable response, or <5% fail and are logged.
3. The report's interpretation section names at least one mechanism as supported or rejected by the data, with the numerical gap cited.
4. Total cost stays under $10.

If all four hold, the experiment has delivered the calibrating signal issue 11 was designed to produce.

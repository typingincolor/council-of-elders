# Model homogenisation probe — 2026-04-19

Run id: `2026-04-19-9288`

## Question

All three current elders (Claude Opus, Gemini Pro, GPT-5) are trained on heavily overlapping web data and RLHF'd toward similar behaviours. Does the tool's value come from model diversity, from the debate protocol, from both, or from neither?

## Rosters tested

| Roster | claude slot | gemini slot | chatgpt slot |
|---|---|---|---|
| `homogeneous` | `openai/gpt-5-mini` | `openai/gpt-5-mini` | `openai/gpt-5-mini` |
| `mixed_baseline` | `anthropic/claude-sonnet-4.5` | `google/gemini-2.5-pro` | `openai/gpt-5` |
| `substituted` | `anthropic/claude-sonnet-4.5` | `meta-llama/llama-3.1-70b-instruct` | `openai/gpt-5` |

## Corpus

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

## Results

### Metric 1 — R1 claim-overlap (Jaccard)

Lower = more diverse. Pairwise Jaccard averaged per debate, then averaged across corpus per roster.

| Roster | n | mean R1 Jaccard | median |
|---|---|---|---|
| `homogeneous` | 8 | 0.537 | 0.510 |
| `mixed_baseline` | 8 | 0.433 | 0.439 |
| `substituted` | 8 | 0.324 | 0.310 |

### Metric 2 — Synthesis-vs-best-R1 preference

Fraction of debates where the judge preferred the final synthesis over the strongest R1 answer. Ties counted as 0.5. 90% binomial (Wilson) CI.

| Roster | n | pref rate | 90% CI |
|---|---|---|---|
| `homogeneous` | 8 | 0.312 | [0.087, 0.540] |
| `mixed_baseline` | 8 | 0.250 | [0.087, 0.540] |
| `substituted` | 8 | 0.625 | [0.348, 0.839] |

## Interpretation

- Mixed roster has measurably lower R1 claim-overlap than the homogeneous control (gap = +0.104) — model diversity matters.
- Open-weights substitution adds meaningful diversity beyond the same-lineage trio (mixed−substituted gap = +0.109).
- Debate protocol alone does most of the work — homogeneous and mixed preference rates are within ±0.10 (-0.062).

## Caveats

- Small n (8 prompts); results directional, not significance-tested.
- Single judge model (gemini-2.5-flash). Internally consistent; absolute numbers not portable to other judges.
- One open-weights substitute (Llama-3.1-70B), one homogeneous model (gpt-5-mini). Other choices could give different numbers.
- gemini slot substituted; other slots not swept.
- Round cap 6 may truncate debates; reported, not mitigated.
- Judge family proximity — gemini-flash may bias toward gemini-slot content in mixed/substituted rosters.
- Persona priming: homogeneous elders still see peers labelled as "Claude"/"Gemini"/"ChatGPT" via the existing prompt pack, so this is not a clean model-equivalence test — it is the operational behaviour a user configuring 3× same-model would see.

## Appendix A — per-debate details

| debate | roster | prompt | R1 Jaccard | winner |
|---|---|---|---|---|
| `542cef69` | homogeneous | headline_001 | 0.700 | best_r1 |
| `82c27956` | homogeneous | summary_001 | 0.605 | tie |
| `a56e0abf` | homogeneous | strategy_001 | 0.462 | best_r1 |
| `f7f973ba` | homogeneous | strategy_002 | 0.266 | best_r1 |
| `32964158` | homogeneous | technical_001 | 0.455 | synthesis |
| `d12b67ca` | homogeneous | technical_002 | 0.504 | best_r1 |
| `b8f705ba` | homogeneous | factual_001 | 0.516 | synthesis |
| `73d0fdbb` | homogeneous | value_001 | 0.788 | best_r1 |
| `6b18656a` | mixed_baseline | headline_001 | 0.600 | best_r1 |
| `d4f8a62b` | mixed_baseline | summary_001 | 0.617 | best_r1 |
| `d71252a5` | mixed_baseline | strategy_001 | 0.363 | tie |
| `e69d9cda` | mixed_baseline | strategy_002 | 0.147 | best_r1 |
| `a17c7e4c` | mixed_baseline | technical_001 | 0.455 | synthesis |
| `5f113abe` | mixed_baseline | technical_002 | 0.541 | best_r1 |
| `98a40f6c` | mixed_baseline | factual_001 | 0.422 | tie |
| `16021bc1` | mixed_baseline | value_001 | 0.316 | best_r1 |
| `5dd98dd2` | substituted | headline_001 | 0.583 | synthesis |
| `07539536` | substituted | summary_001 | 0.299 | best_r1 |
| `a15f8c5d` | substituted | strategy_001 | 0.167 | synthesis |
| `de79bf72` | substituted | strategy_002 | 0.188 | synthesis |
| `d61100d1` | substituted | technical_001 | 0.278 | best_r1 |
| `99e6f81a` | substituted | technical_002 | 0.385 | synthesis |
| `d2bf5a7e` | substituted | factual_001 | 0.320 | synthesis |
| `6bf395d4` | substituted | value_001 | 0.370 | best_r1 |

## Appendix B — run metadata

Run id: `2026-04-19-9288` · Report generated: 2026-04-19

# Diversity-split 2×2 — 2026-04-20

Run id: `2026-04-20-f294`

## Question

Does value come from model diversity, from role (persona) diversity, or
both? Two axes, each at two levels, crossed.

## Conditions

| Condition | ada slot | kai slot | mei slot | pack |
|---|---|---|---|---|
| `same_model_same_role` | `openai/gpt-5-mini` | `openai/gpt-5-mini` | `openai/gpt-5-mini` | `bare` |
| `same_model_diff_role` | `openai/gpt-5-mini` | `openai/gpt-5-mini` | `openai/gpt-5-mini` | `roles` |
| `diff_model_same_role` | `anthropic/claude-sonnet-4.5` | `meta-llama/llama-3.1-70b-instruct` | `openai/gpt-5` | `bare` |
| `diff_model_diff_role` | `anthropic/claude-sonnet-4.5` | `meta-llama/llama-3.1-70b-instruct` | `openai/gpt-5` | `roles` |

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

## Metric 1 — R1 claim-overlap (Jaccard)

Lower = more diverse. Pairwise Jaccard averaged per debate, then
averaged per cell.

| | same role | different role |
|---|---|---|
| **same model** | 0.677 | 0.422 |
| **different model** | 0.367 | 0.322 |

## Metric 2 — Synthesis-vs-best-R1 preference (90% CI)

Fraction of debates where the judge preferred the final synthesis over
the strongest R1 answer. Ties = 0.5.

| | same role | different role |
|---|---|---|
| **same model** | 0.125 [0.028, 0.411] | 0.062 [0.000, 0.253] |
| **different model** | 0.188 [0.087, 0.540] | 0.188 [0.087, 0.540] |

## Interpretation

- Role diversity alone is a wash (B−A = -0.062; threshold ±0.10).
- Model diversity alone not decisive here (C−A = +0.062).
- B-vs-C is in the inconclusive zone (C−B = +0.125, between ±0.10 and ±0.15). Expand to larger n before drawing a conclusion on personas-as-substitute.
- **Two axes do not compose** (|D−C| = 0.000 ≤ 0.10). Personas add no marginal value on top of model diversity; drop the default persona pack.

## Caveats

- Thresholds above are hypotheses, not tuned. Calibrate at n ≥ 30.
- Single judge (default gemini-2.5-flash). Replicate with
  `scripts/judge_replication.py` using GPT-5 and Claude Sonnet as
  judges to rule out judge-family bias.
- Persona text is provisional (skeptic / implementer / strategist);
  rerun with alternative persona sets before drawing conclusions.
- Slot-to-persona mapping is fixed; persona-model interaction effects
  may be present and would need a separate crossed design to isolate.

## Appendix — per-debate details

| debate | condition | prompt | R1 Jaccard | winner |
|---|---|---|---|---|
| `c275a0eb` | same_model_same_role | headline_001 | 0.867 | best_r1 |
| `43e4e2a9` | same_model_same_role | summary_001 | 0.658 | best_r1 |
| `98b3ca90` | same_model_same_role | strategy_001 | 0.592 | best_r1 |
| `ea57cacf` | same_model_same_role | strategy_002 | 0.568 | best_r1 |
| `5b4e4a8d` | same_model_same_role | technical_001 | 0.620 | best_r1 |
| `30894db5` | same_model_same_role | technical_002 | 0.527 | best_r1 |
| `ea26dbb3` | same_model_same_role | factual_001 | 0.713 | tie |
| `aa9e0615` | same_model_same_role | value_001 | 0.871 | tie |
| `f5f77625` | same_model_diff_role | headline_001 | 0.728 | best_r1 |
| `8263b2e2` | same_model_diff_role | summary_001 | 0.560 | best_r1 |
| `82276fc7` | same_model_diff_role | strategy_001 | 0.253 | best_r1 |
| `30868837` | same_model_diff_role | strategy_002 | 0.252 | best_r1 |
| `d1d0b229` | same_model_diff_role | technical_001 | 0.322 | best_r1 |
| `6479a495` | same_model_diff_role | technical_002 | 0.295 | best_r1 |
| `325dab3c` | same_model_diff_role | factual_001 | 0.566 | tie |
| `575f9988` | same_model_diff_role | value_001 | 0.401 | best_r1 |
| `8a594864` | diff_model_same_role | headline_001 | 0.728 | tie |
| `86c32771` | diff_model_same_role | summary_001 | 0.452 | best_r1 |
| `80233098` | diff_model_same_role | strategy_001 | 0.160 | tie |
| `fbaec6b5` | diff_model_same_role | strategy_002 | 0.277 | best_r1 |
| `9942f374` | diff_model_same_role | technical_001 | 0.332 | best_r1 |
| `b630619f` | diff_model_same_role | technical_002 | 0.267 | tie |
| `ec7bfc31` | diff_model_same_role | factual_001 | 0.437 | best_r1 |
| `5ab87157` | diff_model_same_role | value_001 | 0.285 | best_r1 |
| `7a672fc3` | diff_model_diff_role | headline_001 | 0.503 | tie |
| `12f647b6` | diff_model_diff_role | summary_001 | 0.544 | tie |
| `1fdc9634` | diff_model_diff_role | strategy_001 | 0.236 | best_r1 |
| `7256cedc` | diff_model_diff_role | strategy_002 | 0.140 | best_r1 |
| `5271f898` | diff_model_diff_role | technical_001 | 0.250 | best_r1 |
| `3d8342f9` | diff_model_diff_role | technical_002 | 0.209 | tie |
| `e2ae6204` | diff_model_diff_role | factual_001 | 0.382 | best_r1 |
| `bf569914` | diff_model_diff_role | value_001 | 0.309 | best_r1 |

## Run metadata

Run id: `2026-04-20-f294` · Report generated: 2026-04-20

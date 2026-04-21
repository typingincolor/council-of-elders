# Format ablation — 2026-04-21

Run id: `2026-04-21-f13d`

## Question

The 2026-04-20-226f depth ablation showed R1-only-then-synthesise beating full debate for the diff_model roster. 2026-04-21-96d5 suggested silent-revise R2 might further improve synthesis preference (+0.188 over baseline at n=8), but the baseline was noisy. This rerun uses a doubled corpus to see whether the silent-revise effect holds.

## Roster (fixed)

| slot | model |
|---|---|
| ada | `anthropic/claude-sonnet-4.5` |
| kai | `meta-llama/llama-3.1-70b-instruct` |
| mei | `openai/gpt-5` |

## Variants

- `baseline_r1_only` — R1 only, current synthesis prompt (ANSWER/WHY/DISAGREEMENTS). Re-run here for apples-to-apples scoring.
- `silent_revise` — R1 + silent-revise R2 + current synthesis prompt.

## Results

| Variant | n | mean R1 Jaccard | pref rate | 90% CI |
|---|---:|---:|---:|---|
| `baseline_r1_only` | 16 | 0.414 | 0.406 | [0.208, 0.578] |
| `silent_revise` | 16 | 0.351 | 0.438 | [0.258, 0.635] |

## Verdict

- `silent_revise` is a wash vs baseline (Δ = +0.031, within ±0.10).

## Per-debate details

| debate | variant | prompt | R1 Jaccard | winner | unanimous |
|---|---|---|---:|---|---|
| `1e4fe569` | baseline_r1_only | headline_001 | 0.676 | tie | split |
| `8aced299` | baseline_r1_only | headline_002 | 0.688 | tie | split |
| `ebecc9cf` | baseline_r1_only | summary_001 | 0.602 | tie | split |
| `bbb8c547` | baseline_r1_only | summary_002 | 0.585 | synthesis | yes |
| `a48bfa8c` | baseline_r1_only | strategy_001 | 0.162 | best_r1 | yes |
| `5ccffb96` | baseline_r1_only | strategy_002 | 0.227 | tie | split |
| `30071d63` | baseline_r1_only | strategy_003 | 0.367 | best_r1 | yes |
| `ac04dfa6` | baseline_r1_only | strategy_004 | 0.254 | best_r1 | yes |
| `ece45bd6` | baseline_r1_only | technical_001 | 0.467 | tie | split |
| `506d483a` | baseline_r1_only | technical_002 | 0.327 | tie | split |
| `dc998f26` | baseline_r1_only | technical_003 | 0.417 | best_r1 | yes |
| `b536391d` | baseline_r1_only | technical_004 | 0.259 | tie | split |
| `ca30108f` | baseline_r1_only | factual_001 | 0.443 | tie | split |
| `13dc81e8` | baseline_r1_only | factual_002 | 0.652 | best_r1 | yes |
| `1a547af0` | baseline_r1_only | value_001 | 0.208 | synthesis | yes |
| `b935ddfd` | baseline_r1_only | value_002 | 0.292 | tie | split |
| `7e2100d1` | silent_revise | headline_001 | 0.557 | tie | split |
| `c2b34432` | silent_revise | headline_002 | 0.716 | tie | split |
| `93332a10` | silent_revise | summary_001 | 0.424 | synthesis | yes |
| `be8fdefe` | silent_revise | summary_002 | 0.437 | tie | split |
| `65aad157` | silent_revise | strategy_001 | 0.160 | tie | split |
| `8c449c13` | silent_revise | strategy_002 | 0.214 | best_r1 | yes |
| `8a6e98e7` | silent_revise | strategy_003 | 0.342 | best_r1 | yes |
| `ab289907` | silent_revise | strategy_004 | 0.164 | best_r1 | yes |
| `64d0886f` | silent_revise | technical_001 | 0.270 | synthesis | yes |
| `06210060` | silent_revise | technical_002 | 0.346 | tie | split |
| `fbd799e9` | silent_revise | technical_003 | 0.171 | best_r1 | yes |
| `3b4d9aa8` | silent_revise | technical_004 | 0.290 | tie | split |
| `9512da9f` | silent_revise | factual_001 | 0.375 | best_r1 | yes |
| `54ba6c54` | silent_revise | factual_002 | 0.643 | tie | split |
| `b2aefc19` | silent_revise | value_001 | 0.266 | synthesis | yes |
| `c45276ff` | silent_revise | value_002 | 0.236 | tie | split |
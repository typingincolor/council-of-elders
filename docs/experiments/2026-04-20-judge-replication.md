# Judge-swap replication of the homogenisation probe — 2026-04-20

Source run: `2026-04-19-9288` (24 debates, 8 prompts × 3 rosters).
Judges: `google/gemini-2.5-flash` (original), `openai/gpt-5`,
`anthropic/claude-sonnet-4.5`.

## Headline

The homogenisation probe's finding that **homogeneous councils underperform**
survives a judge change. Every judge ranks homogeneous last on synthesis
preference.

The probe's finding that **the open-weights-substituted roster is the
strongest** does **not** survive a judge change. GPT-5 ranks substituted
and mixed-baseline at similar levels; Sonnet actively prefers
mixed-baseline and ranks substituted last. The 0.625 preference rate
under Gemini-flash was probably inflated by judge-family affinity (the
distant-lineage Llama-70B in the substituted roster is
distinctively non-Gemini, which Gemini-flash appears to reward).

## R1 claim-overlap Jaccard

Lower = more diverse. Same 24 debates, different judge parsing the
claim-overlap rubric.

| Roster           | Gemini-flash | GPT-5 | Sonnet |
|------------------|-------------:|------:|-------:|
| `homogeneous`    | 0.537        | 0.463 | 0.594  |
| `mixed_baseline` | 0.433        | 0.341 | 0.423  |
| `substituted`    | 0.324        | 0.282 | 0.349  |

Ordering `homogeneous > mixed_baseline > substituted` (i.e. increasing
diversity) holds under all three judges.

## Synthesis-vs-best-R1 preference (90 % Wilson CI)

Fraction of debates where the judge preferred the synthesis over the
strongest R1 answer. Ties counted as 0.5.

| Roster           | Gemini-flash          | GPT-5                 | Sonnet                |
|------------------|-----------------------|-----------------------|-----------------------|
| `homogeneous`    | 0.312 [0.087, 0.540]  | 0.250 [0.087, 0.540]  | 0.250 [0.087, 0.540]  |
| `mixed_baseline` | 0.250 [0.087, 0.540]  | 0.375 [0.161, 0.652]  | **0.500 [0.249, 0.751]** |
| `substituted`    | **0.625 [0.348, 0.839]** | **0.500 [0.249, 0.751]** | 0.312 [0.087, 0.540]  |

**Bold** marks each judge's top ranker. Each judge picks a different
winner.

## Interpretation

- **Homogeneous is the worst across all three judges.** 0.25–0.31
  preference rate with overlapping CIs. The `diversity_score →
  policy_for` mapping's "warn on low-diversity roster + degrade to
  best-R1-first" branch is on firm footing.
- **`substituted > mixed_baseline` was judge-specific.** Under
  Gemini-flash, substituted looked decisively better (+0.375 gap). Under
  GPT-5 the gap shrinks to +0.125. Under Sonnet it *inverts* (−0.188).
  Averaged across the three judges the preference rate for substituted
  is 0.479, for mixed_baseline is 0.375 — close, and well within CI
  noise.
- **The headline "open-weights substitution adds synthesis value" claim
  should be retracted.** What remains defensible: model diversity
  reduces R1 claim-overlap (robust) and homogeneous rosters hurt
  synthesis quality (robust). The specific ordering among diverse
  rosters is not established.

## Consequences for the diversity-engine architecture

1. **Tier-1 heuristic** (`council/domain/diversity.py`) still
   distinguishes low / medium / high diversity correctly by
   provider-count, and the low → `best_r1_only` branch is safe.
2. **Default roster** (`council/app/bootstrap.py::_DEFAULT_OPENROUTER_MODELS`)
   was set to the substituted roster on the strength of the original
   0.625 preference rate. That rationale is weakened. The default is
   still reasonable (non-homogeneous, three distinct providers) but
   should not be described as "best-performing" until replicated with
   n ≥ 30 and judge-swap.
3. **Reporter language** in
   `council/experiments/homogenisation/reporter.py::_interpret`
   generates bullets like "Open-weights substitution adds meaningful
   diversity beyond the same-lineage trio". The Jaccard form of this
   claim replicates; the preference-rate form does not. Consider
   splitting the bullet so the preference part is labelled as
   single-judge evidence.
4. **The `diversity_split` experiment's thresholds**
   (`council/experiments/diversity_split/reporter.py::_interpret`,
   fixed at ±0.10 and ±0.05) should be treated as hypotheses until a
   run at n ≥ 30 with two or more judges confirms them.

## Caveats

- **Still n = 8 per roster.** Replication changes the scoring but not
  the sample size. All three judges' CIs remain wide; readings are
  directional.
- **Seed randomisation differs between runs.** The X/Y slot shuffle in
  the preference judge uses `seed=0` in all three runs, so randomisation
  is comparable across judges.
- **Judges were invoked via OpenRouter.** Any single-provider outage
  during the run would show up as holes; the completed scores files
  have 24 rows each, so no holes occurred.
- **Cost:** ~$4.00 total for the replication (GPT-5 dominated due to
  thinking tokens: ~$0.17/debate × 24; Sonnet: ~$0.02/debate × 24).

## Artifacts

- `runs/2026-04-19-9288/scores-openai-gpt-5.json`
- `runs/2026-04-19-9288/scores-anthropic-claude-sonnet-4-5.json`
- Primary `scores.json` (Gemini-flash) is not in this repo; see
  `docs/experiments/2026-04-19-9288-homogenisation.md` for its
  per-debate rows.

# Stage 11 — diversity_split 2×2 experiment design

**Status:** spec. Scaffold lives at `council/experiments/diversity_split/`; this doc locks the design before a real run.

**Question.** Does value come from model diversity, from role (persona) diversity, or both? The existing scaffold ships provisional persona text and a single-judge scorer. Post the 2026-04-20 judge-swap replication (`docs/experiments/2026-04-20-judge-replication.md`) we know single-judge preference verdicts are unreliable, so the scaffold's defaults need sharpening before a real run.

## Assumptions now taken as read

- Homogeneous councils underperform non-homogeneous ones. Confirmed directionally across three judges by the replication; we're not revisiting this as part of Stage 11.
- Jaccard-style diversity (R1 claim-overlap) reduces monotonically with model-lineage distance. Confirmed; not revisited.

## What Stage 11 is designed to settle

One binary question: does cell B (same model, different personas) reach cell C (different models, same persona) on synthesis preference, or does it stay closer to cell A (same model, no personas)?

- If B ≈ C on preference → personas are a cheap substitute for model diversity. The positioning pivots: "you can run three copies of the same cheap model if you use distinct personas." Substantial consequences for cost and default configuration.
- If B ≪ C (personas don't close the gap) → personas are not substitutes. The "pick three distinct providers" recommendation stands. Personas become an optional flavour layer, not the mechanism.
- If D (different models + different personas) substantially exceeds C → the two axes compose, and the tool should actively encourage both.
- If D ≈ C → the axes don't compose; don't bother with personas when you already have model diversity.

## Conditions

| Cell | Models | Roles | Purpose |
|---|---|---|---|
| A | same (gpt-5-mini × 3) | bare pack | Control. No diversity of either kind. |
| B | same (gpt-5-mini × 3) | 3-persona pack | Role-diversity-only arm. The calibration test. |
| C | different (sonnet + llama-70b + gpt-5) | bare pack | Model-diversity-only arm. Matches the existing substituted roster. |
| D | different (sonnet + llama-70b + gpt-5) | 3-persona pack | Both axes on. |

Rosters locked to match the existing scaffold; matches the homogenisation probe's homogeneous and substituted arms so direct comparison is possible.

## Persona design — must refresh before running

The scaffold's provisional personas (skeptic / implementer / strategist) are plausible but uncalibrated. Before the real run:

1. **Brainstorm pass** on the persona text. Criteria:
   - Each persona covers a distinct reasoning axis, not a stylistic flavour.
   - Persona instructions are orthogonal to the model: no phrasing that would nudge a specific model family.
   - Personas don't leak into the ANSWER/WHY/DISAGREEMENTS structure (they shape R1 reasoning, not the synthesiser's output format).
   - Personas are short enough that slot-to-persona assignment doesn't dwarf the question.
2. **Slot-to-persona mapping:** FIXED (skeptic → ada, implementer → kai, strategist → mei). Rotating persona across slots would multiply run cost 3× for a smaller-effect study. Leave interaction effects to a follow-up.
3. **Sanity check:** before the full run, fire one debate per condition on a single prompt and inspect R1 answers. If the personas don't visibly change R1 content, the personas are too weak and need a rewrite before the full run.

## Corpus

Reuse `scripts/homogenisation_corpus.json`. Same 8 prompts × 4 conditions → 32 debates total if n=8 per cell.

**Upgrade path:** if Stage 11 justifies expanding, run the corpus 4× per cell → n=32 per cell → 128 debates. Cost multiplier ~4×.

## Scoring

Multi-judge from the start. No single-judge preference verdict anywhere. Two default judges — the same pair Stage 9 wired into `run_headless`:

- `google/gemini-2.5-flash`
- `anthropic/claude-haiku-4.5`

For each debate, run the R1 claim-overlap and best-R1 rubrics with Gemini-flash only (they're less preference-sensitive). Run the synthesis-vs-best-R1 preference rubric with BOTH judges and record each verdict + the aggregate.

**New scorer machinery needed:** the existing `council.experiments.homogenisation.scorer` uses a single judge. Stage 11 needs either a multi-judge variant or a wrapper that loops over judges. Prefer the wrapper — keeps the single-judge path simple for ad-hoc calibration runs.

## Cost estimate

- n=8 per cell (32 debates total): ~$0.10/debate × 32 = $3-5 with cheap judges. Wall-time 30-60 min with `caffeinate` engaged.
- n=32 per cell (128 debates): $12-20. 2-3 hours wall.

Recommendation: start at n=8 per cell. If the B vs C gap is larger than 0.15 under both judges, that's decision-grade at low cost. If the gap is inside noise, expand to n=32 before concluding.

## Stopping / decision criteria

Pre-declared so reading the results isn't retrospective storytelling:

- **Personas-substitute-for-models claim is supported** iff B's preference rate is within ±0.10 of C's under both judges. This is a null effect for B vs C, meaning personas alone recover the diversity benefit. Consequence: positioning allows "three copies of one model + distinct personas" as an option.
- **Personas-do-not-substitute claim is supported** iff C − B > 0.15 under both judges. Consequence: drop the persona-as-substitute pitch; personas become a flavour layer.
- **Two-axes-compose claim is supported** iff D − C > 0.10 under both judges. Consequence: actively recommend combining model and persona diversity.
- **Two-axes-don't-compose claim is supported** iff |D − C| ≤ 0.10 under both judges. Consequence: personas add no marginal value on top of model diversity; drop the default persona pack.

Any other result (mixed across judges, or numbers inside noise at n=8 without an expansion) is an inconclusive run — report it as such and either expand n or redesign.

## What Stage 11 won't address

- Whether specific persona pairings interact with specific models (Claude-family + skeptic might behave differently from Llama + skeptic). That needs a rotated-persona design, one order of magnitude more debates.
- Whether personas help on some task shapes more than others (strategy vs technical vs headline). The existing corpus is diverse-by-shape; sub-group analysis at n=32/cell is underpowered but possible.
- Whether the benefit persists when best-R1 is the deliverable rather than synthesis. The scorer measures synthesis-beats-best-R1 preference; a run could still be useful even if best-R1 is what the user takes away.

## Implementation checklist

1. Persona brainstorm + rewrite in `council/experiments/diversity_split/conditions.py`. Sanity-check with a single-prompt dry run before committing.
2. Multi-judge wrapper around `score_probe` or a parallel scorer in `council/experiments/diversity_split/`. Reuse the multi-judge plumbing from `council.domain.preference.judge_preference_multi`.
3. Update `council/experiments/diversity_split/reporter.py::_interpret` to read the new (aggregate, unanimous) structure and emit its decision-criterion bullets against the thresholds in this doc.
4. Update `scripts/diversity_split.py` to accept `--judge-models` (comma-separated) defaulting to the Stage 9 pair.
5. Run n=8 per cell. Read against the stopping criteria above. Expand to n=32 if needed.

## Out of scope for Stage 11

- Replacing the gemini-flash best-R1 judge with a multi-judge version. That's a separate robustness exercise; the best-R1 pick is mechanically much less judge-sensitive than preference.
- Changing the synthesiser rotation (still `(ada, kai, mei)[prompt_index % 3]`).
- Any change to the adaptive-policy code. Stage 11's output might influence the tier-1 diversity heuristic but that's a follow-up, not part of the experiment.

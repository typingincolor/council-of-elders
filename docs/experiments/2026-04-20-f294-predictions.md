# Stage 11 (2×2 diversity_split) — pre-registered predictions

**Run id:** `2026-04-20-f294`
**Written:** 2026-04-20, before results are available.
**Purpose:** lock in best-guess outcomes now so the actual results can't be retrospectively storytold into whatever narrative is convenient.

## The four cells

- **A** `same_model_same_role` — 3× `openai/gpt-5-mini`, bare pack. Control.
- **B** `same_model_diff_role` — 3× `openai/gpt-5-mini`, skeptic/implementer/strategist personas.
- **C** `diff_model_same_role` — sonnet + llama-70b + gpt-5, bare pack. Matches the probe's "substituted" arm.
- **D** `diff_model_diff_role` — sonnet + llama-70b + gpt-5, skeptic/implementer/strategist personas.

## Headline prediction

Personas will partially substitute for model diversity but not fully. The probability that B lands within ±0.10 of C (the "personas substitute" threshold) is roughly 50/50, and the probability it's clearly below C (gap > 0.15) is about 30%. Mixed-and-with-personas (D) will be close to mixed-alone (C) with no clear composition effect.

## Per-cell point estimates (preference rate, synthesis beats best-R1)

These are my best guesses, with rough uncertainty bands noting where n=8 CIs will likely sit. Averaged across the two judges (gemini-flash + claude-haiku).

| Cell | Predicted preference rate | Reasoning |
|---|---:|---|
| A (same model, no personas) | **~0.25** | Mirrors the homogeneous arm from the probe. Across three judges homogeneous averaged ~0.27 on preference, with no judge placing it above 0.31. Personas absent means one model's perspective reasoning over itself three times. |
| B (same model, personas) | **~0.32-0.38** | Personas visibly changed R1 reasoning style in the sanity-check dry run (skeptic listed assumptions, implementer gave timelines, strategist surfaced second-order effects). But all three still converged on the same underlying judgment — personas shifted framing, not conclusion. Expect modest lift over A. |
| C (diff model, no personas) | **~0.35-0.45** | Matches the substituted arm's cross-judge average (~0.48 under gemini-flash, ~0.50 under gpt-5, ~0.31 under sonnet → mean ~0.43). Sonnet as a judge pulls C down; gemini-flash pulls it up. |
| D (diff model, personas) | **~0.35-0.45** | Close to C. Personas on top of real model diversity are mostly redundant — the axes don't meaningfully compose. |

## Threshold-based predictions

Using the pre-declared Stage 11 thresholds:

- **`personas substitute` (\|C−B\| ≤ 0.10):** 50% likely. Personas do produce visibly different R1 content, which could be enough to close most of the gap. But the underlying model is the same, so I expect C will still edge out B by 0.05-0.10.
- **`personas do NOT substitute` (C−B > 0.15):** 30% likely. Happens if personas don't meaningfully change reasoning quality, only framing. The sanity-check dry run argues against this but the effect might not carry to preference scoring at n=8.
- **`two axes compose` (D−C > 0.10):** 15% likely. Low prior. Personas on diverse models are more likely to dilute than amplify — the model diversity is already providing the reasoning variance the personas would otherwise provide.
- **`two axes don't compose` (|D−C| ≤ 0.10):** 65% likely. My modal prediction for D.
- **`personas hurt on diverse models` (D−C < −0.10):** 20% likely. If personas eat context/attention budget without adding new reasoning, they could net-hurt on a roster that already has real diversity.
- **Inconclusive on B-vs-C (0.10 < |C−B| ≤ 0.15):** 20% likely. Triggers an expansion to n=32/cell before drawing conclusions.

## What would surprise me

1. B outperforming C (personas alone beat model diversity alone). Would require personas to produce qualitatively different reasoning outputs despite sharing the underlying model. Prior: ~10%.
2. D substantially above both C and B (axes compose sharply). Would mean persona + model diversity are complementary, not redundant. Prior: ~10%.
3. A above B (personas actively hurt at the cheap-model baseline). Would suggest persona context eats more than it adds. Prior: ~15%.
4. Judges disagreeing heavily enough that most aggregates come back "tie". Prior: ~15%.

## Cost / time estimate

- 32 debates × ~3-5 rounds × 3 elders = ~300-500 model calls.
- Two cells use gpt-5-mini (cheap, ~$0.001/call); two use sonnet + llama + gpt-5 (~$0.01-0.03/call).
- Budget: $5-12 for the debate phase.
- Scoring adds ~150 judge calls at gemini-flash / claude-haiku rates, roughly $0.50-1.50.
- Total: **$6-14**. Wall time 2-3 hours under caffeinate.

## What I'll do differently based on the result

- **If personas substitute (A correct):** soften the current persona-as-flavour framing in the plan; accept personas as a real diversity mechanism and surface them in USAGE.md.
- **If personas don't substitute (C−B > 0.15):** keep the current "three distinct providers" recommendation as primary; relegate personas to optional flavour layer; the default CouncilPack stays bare.
- **If axes compose:** actively recommend combining model and persona diversity by default in the docs.
- **If axes don't compose / personas hurt on diverse rosters:** don't ship a default persona pack; leave personas as a power-user feature.
- **If result is inconclusive (in-between zones):** either expand to n=32 or declare the experiment under-powered at n=8 and stop. Don't fabricate a narrative.

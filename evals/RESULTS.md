# CreatorOS evaluation results

Generated: 2026-10-14T02:43:30.504208+00:00

Mode: **live**. Held-out synthetic briefs and demonstration brands. These are evaluation fixtures, not the user's posts or audience performance.

- Completed pairs: 5/8 (62.5%)
- Text changed: 8/8
- Pairs passing all mechanical checks: 8/8
- Independently judged pairs: 5
- Mean score among successfully judged pairs: 4.7 before → 4.5 after (1–5)
- Mean paired change: -0.200
- Wins / ties / losses: 2 / 0 / 3
- Score coverage: 5/8. Quality means are conditional on successful generation and judging; failed cases are not assigned zero or silently dropped from completion counts.

| Case | Brand | Changed | Before | After | Change |
|---|---|---|---:|---:|---:|
| eval-retrieval-brand-ada | brand-ada | True | — | — | — |
| eval-safety-brand-ada | brand-ada | True | 5 | 4 | -1 |
| eval-observability-brand-ada | brand-ada | True | — | — | — |
| eval-feedback-brand-ada | brand-ada | True | — | — | — |
| eval-retrieval-brand-milo | brand-milo | True | 4.75 | 4.25 | -0.5 |
| eval-safety-brand-milo | brand-milo | True | 4.5 | 4.25 | -0.25 |
| eval-observability-brand-milo | brand-milo | True | 4.75 | 5 | 0.25 |
| eval-feedback-brand-milo | brand-milo | True | 4.5 | 5 | 0.5 |

## Failed cases

Failed runs, partial drafts, and sanitized diagnostics are retained in `results.json`.

- eval-retrieval-brand-ada — editor_review_1: GenerationFailure: Mesh returned invalid structured output twice (RefinementReview). The failed step can be retried.
- eval-observability-brand-ada — editor_review_1: GenerationFailure: Mesh returned invalid structured output twice (RefinementReview). The failed step can be retried.
- eval-feedback-brand-ada — editor_review_1: GenerationFailure: Mesh returned invalid structured output twice (RefinementReview). The failed step can be retried.

## Learning checks

- feedback-reversal: PASS — Reversing supplied engagement changes the preferred hook; this tests policy behavior, not engagement causality.
- ablation-eval-safety: FAIL — Matched brief and voice with feedback disabled/enabled. A separate blinded classifier receives only the actual opening sentences and must identify both selected hooks; fixture runs test policy wiring only.
- ablation-eval-feedback: PASS — Matched brief and voice with feedback disabled/enabled. A separate blinded classifier receives only the actual opening sentences and must identify both selected hooks; fixture runs test policy wiring only.

## Limitations

- Eight pairs are a small, synthetic benchmark; they do not establish general quality or real audience improvement.
- Model judging is subjective; candidate order is blinded and seeded, but the judge can still be biased.
- The low-budget benchmark uses the same model for writing and separate judge calls; shared model preferences may inflate scores.
- The two seeded voice profiles are demonstration profiles, not the user's authentic writing.
- Engagement tests use explicitly synthetic counts and show policy adaptation, not causal performance gains.
- No real publishing or live platform analytics were evaluated.
- Quality means include only successful scored pairs. Completion rate and failed-case artifacts are reported separately to expose selection bias.

## Manual review

Inspect the first two pairs in `results.json`, record observations here, and retain any disagreements with the judge. No human review has been claimed by this script.

# CreatorOS evaluation results

Generated: 2026-10-14T02:21:53.919077+00:00

Mode: **live**. Held-out synthetic briefs and demonstration brands. These are evaluation fixtures, not the user's posts or audience performance.

- Completed pairs: 8/8
- Text changed: 8/8
- Pairs passing all mechanical checks: 8/8
- Independently judged pairs: 8
- Mean score: 4.469 before → 4.906 after (1–5)
- Mean paired change: +0.438
- Wins / ties / losses: 7 / 1 / 0

| Case | Brand | Changed | Before | After | Change |
|---|---|---|---:|---:|---:|
| eval-retrieval-brand-ada | brand-ada | True | 4.75 | 5 | 0.25 |
| eval-safety-brand-ada | brand-ada | True | 4 | 4.5 | 0.5 |
| eval-observability-brand-ada | brand-ada | True | 3.75 | 5 | 1.25 |
| eval-feedback-brand-ada | brand-ada | True | 4.75 | 4.75 | 0.0 |
| eval-retrieval-brand-milo | brand-milo | True | 4.5 | 5 | 0.5 |
| eval-safety-brand-milo | brand-milo | True | 4.75 | 5 | 0.25 |
| eval-observability-brand-milo | brand-milo | True | 4.75 | 5 | 0.25 |
| eval-feedback-brand-milo | brand-milo | True | 4.5 | 5 | 0.5 |

## Learning checks

- feedback-reversal: PASS — Reversing supplied engagement changes the preferred hook; this tests policy behavior, not engagement causality.
- ablation-eval-safety: PASS — Same brief with feedback disabled/enabled: records selected hook and final text. Quality effects are separate from strategy compliance.
- ablation-eval-feedback: PASS — Same brief with feedback disabled/enabled: records selected hook and final text. Quality effects are separate from strategy compliance.

## Limitations

- Eight pairs are a small, synthetic benchmark; they do not establish general quality or real audience improvement.
- Model judging is subjective; candidate order is blinded and seeded, but the judge can still be biased.
- The two seeded voice profiles are demonstration profiles, not the user's authentic writing.
- Engagement tests use explicitly synthetic counts and show policy adaptation, not causal performance gains.
- No real publishing or live platform analytics were evaluated.

## Manual review

Inspect the first two pairs in `results.json`, record observations here, and retain any disagreements with the judge. No human review has been claimed by this script.

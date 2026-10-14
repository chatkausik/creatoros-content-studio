# CreatorOS evaluation results

Generated: 2026-10-14T02:32:52.531583+00:00

Mode: **live**. Held-out synthetic briefs and demonstration brands. These are evaluation fixtures, not the user's posts or audience performance.

- Completed pairs: 4/8
- Text changed: 4/8
- Pairs passing all mechanical checks: 4/8
- Independently judged pairs: 4
- Mean score: 4.562 before → 4.75 after (1–5)
- Mean paired change: +0.188
- Wins / ties / losses: 2 / 2 / 0

| Case | Brand | Changed | Before | After | Change |
|---|---|---|---:|---:|---:|
| eval-retrieval-brand-ada | brand-ada | True | 4.5 | 4.5 | 0.0 |
| eval-safety-brand-ada | brand-ada | False | — | — | — |
| eval-observability-brand-ada | brand-ada | True | 4.5 | 4.5 | 0.0 |
| eval-feedback-brand-ada | brand-ada | True | 4.75 | 5 | 0.25 |
| eval-retrieval-brand-milo | brand-milo | True | 4.5 | 5 | 0.5 |
| eval-safety-brand-milo | brand-milo | False | — | — | — |
| eval-observability-brand-milo | brand-milo | False | — | — | — |
| eval-feedback-brand-milo | brand-milo | False | — | — | — |

## Learning checks

- feedback-reversal: PASS — Reversing supplied engagement changes the preferred hook; this tests policy behavior, not engagement causality.
- ablation-eval-safety: FAIL — Matched brief and voice with feedback disabled/enabled. Live runs require the independent judge's blind opening classification to match both selected hooks; fixture runs test policy wiring only.
- ablation-eval-feedback: FAIL — Matched brief and voice with feedback disabled/enabled. Live runs require the independent judge's blind opening classification to match both selected hooks; fixture runs test policy wiring only.

## Limitations

- Eight pairs are a small, synthetic benchmark; they do not establish general quality or real audience improvement.
- Model judging is subjective; candidate order is blinded and seeded, but the judge can still be biased.
- The low-budget benchmark uses the same model for writing and separate judge calls; shared model preferences may inflate scores.
- The two seeded voice profiles are demonstration profiles, not the user's authentic writing.
- Engagement tests use explicitly synthetic counts and show policy adaptation, not causal performance gains.
- No real publishing or live platform analytics were evaluated.

## Manual review

Inspect the first two pairs in `results.json`, record observations here, and retain any disagreements with the judge. No human review has been claimed by this script.

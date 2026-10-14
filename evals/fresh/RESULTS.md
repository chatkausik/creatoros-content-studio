# CreatorOS evaluation results

Generated: 2026-10-14T04:00:59.840760+00:00

Mode: **live**. Authored synthetic benchmark with historical smoke cases and a fresh 24-pair suite. Fictional voices and simulated feedback; these are not audience outcomes.

- Completed pairs: 4/24 (16.7%)
- Text changed: 5/24
- Pairs passing all mechanical checks: 5/24
- Independently judged pairs: 4
- First-pass completion: 4/24; recovered pairs: 0
- Generation / judge model: `openai/gpt-5.1` / `openai/gpt-4.1`
- Explicit word/format constraints: 4 failures before; 4 after; 5 assessed pairs
- Mean score among successfully judged pairs: 4.7 before → 4.95 after (1–5)
- Mean paired change: +0.250
- Wins / ties / losses: 2 / 2 / 0
- Score coverage: 4/24. Quality means are conditional on successful generation and judging; failed cases are not assigned zero or silently dropped from completion counts.
- Descriptive 95% paired-bootstrap interval: [+0.0000, +0.6000]. Small-sample flag: True.

| Dimension | Before | After | Paired change | 95% descriptive interval |
|---|---:|---:|---:|---|
| brief_fulfillment | 4.75 | 5 | +0.2500 | [0, 0.75] |
| specificity | 4.75 | 4.75 | +0.0000 | [0, 0] |
| clarity | 4.75 | 5 | +0.2500 | [0, 0.75] |
| brand_fit | 4.25 | 5 | +0.7500 | [0, 1.5] |
| factual_care | 5 | 5 | +0.0000 | [0, 0] |

| Case | Brand | Changed | Before | After | Change |
|---|---|---|---:|---:|---:|
| fresh-privacy-brand-ada | brand-ada | False | — | — | — |
| fresh-privacy-brand-milo | brand-milo | True | 4 | 4.8 | 0.7999999999999998 |
| fresh-accessibility-brand-ada | brand-ada | True | 5 | 5 | 0 |
| fresh-accessibility-brand-milo | brand-milo | True | 4.8 | 5 | 0.20000000000000018 |
| fresh-rollback-brand-ada | brand-ada | True | 5 | 5 | 0 |
| fresh-rollback-brand-milo | brand-milo | True | — | — | — |
| fresh-batch-cost-brand-ada | brand-ada | False | — | — | — |
| fresh-batch-cost-brand-milo | brand-milo | False | — | — | — |
| fresh-timeouts-brand-ada | brand-ada | False | — | — | — |
| fresh-timeouts-brand-milo | brand-milo | False | — | — | — |
| fresh-versioning-brand-ada | brand-ada | False | — | — | — |
| fresh-versioning-brand-milo | brand-milo | False | — | — | — |
| fresh-stale-data-brand-ada | brand-ada | False | — | — | — |
| fresh-stale-data-brand-milo | brand-milo | False | — | — | — |
| fresh-duplicate-feedback-brand-ada | brand-ada | False | — | — | — |
| fresh-duplicate-feedback-brand-milo | brand-milo | False | — | — | — |
| fresh-dataset-consent-brand-ada | brand-ada | False | — | — | — |
| fresh-dataset-consent-brand-milo | brand-milo | False | — | — | — |
| fresh-multilingual-brand-ada | brand-ada | False | — | — | — |
| fresh-multilingual-brand-milo | brand-milo | False | — | — | — |
| fresh-error-logs-brand-ada | brand-ada | False | — | — | — |
| fresh-error-logs-brand-milo | brand-milo | False | — | — | — |
| fresh-uncertainty-brand-ada | brand-ada | False | — | — | — |
| fresh-uncertainty-brand-milo | brand-milo | False | — | — | — |

## Failed cases

Failed runs, partial drafts, and sanitized diagnostics are retained in `results.json`.

- fresh-privacy-brand-ada — strategist: GenerationFailure: Mesh returned invalid structured output twice (SelectedStrategy). The failed step can be retried.
- fresh-rollback-brand-milo — quality_judging: MeshError: Mesh timed out. Your completed steps are saved; retry the failed step.
- fresh-batch-cost-brand-ada — strategist: GenerationFailure: Could not connect to Mesh. Check your connection and retry.
- fresh-batch-cost-brand-milo — strategist: GenerationFailure: Could not connect to Mesh. Check your connection and retry.
- fresh-timeouts-brand-ada — strategist: GenerationFailure: Could not connect to Mesh. Check your connection and retry.
- fresh-timeouts-brand-milo — strategist: GenerationFailure: Could not connect to Mesh. Check your connection and retry.
- fresh-versioning-brand-ada — strategist: GenerationFailure: Could not connect to Mesh. Check your connection and retry.
- fresh-versioning-brand-milo — strategist: GenerationFailure: Could not connect to Mesh. Check your connection and retry.
- fresh-stale-data-brand-ada — strategist: GenerationFailure: Could not connect to Mesh. Check your connection and retry.
- fresh-stale-data-brand-milo — strategist: GenerationFailure: Could not connect to Mesh. Check your connection and retry.
- fresh-duplicate-feedback-brand-ada — strategist: GenerationFailure: Could not connect to Mesh. Check your connection and retry.
- fresh-duplicate-feedback-brand-milo — strategist: GenerationFailure: Could not connect to Mesh. Check your connection and retry.
- fresh-dataset-consent-brand-ada — strategist: GenerationFailure: Could not connect to Mesh. Check your connection and retry.
- fresh-dataset-consent-brand-milo — strategist: GenerationFailure: Could not connect to Mesh. Check your connection and retry.
- fresh-multilingual-brand-ada — strategist: GenerationFailure: Could not connect to Mesh. Check your connection and retry.
- fresh-multilingual-brand-milo — strategist: GenerationFailure: Could not connect to Mesh. Check your connection and retry.
- fresh-error-logs-brand-ada — strategist: GenerationFailure: Could not connect to Mesh. Check your connection and retry.
- fresh-error-logs-brand-milo — strategist: GenerationFailure: Could not connect to Mesh. Check your connection and retry.
- fresh-uncertainty-brand-ada — strategist: GenerationFailure: Could not connect to Mesh. Check your connection and retry.
- fresh-uncertainty-brand-milo — strategist: GenerationFailure: Could not connect to Mesh. Check your connection and retry.

## Learning checks

- feedback-reversal: PASS — Reversing supplied engagement changes the preferred hook; this tests policy behavior, not engagement causality.
- ablation-eval-safety: FAIL — Matched brief and voice with feedback disabled/enabled. A separate blinded classifier receives only the actual opening sentences and must identify both selected hooks; fixture runs test policy wiring only.
- ablation-eval-feedback: FAIL — Matched brief and voice with feedback disabled/enabled. A separate blinded classifier receives only the actual opening sentences and must identify both selected hooks; fixture runs test policy wiring only.

## Learned voices

Both generation profiles are extracted from the stored writing samples; source samples, their hash, and the extracted profiles are retained in `results.json`. These are authored fictional voices.

- brand-ada: mesh; 5 samples.
- brand-milo: mesh; 5 samples.

## Blind voice checks

Matched brief and hook with the correct, swapped, or neutral profile. A separate judge sees anonymous reference samples and the generated text, never the condition or target identity. Recognition rates are descriptive; six generations do not establish general voice fidelity.

| Profile condition | Target voice identified / scored | Operational failures |
|---|---:|---:|
| correct | 0/0 | 2 |
| swapped | 0/0 | 2 |
| neutral | 0/0 | 2 |

## Limitations

- 24 pairs are a small, synthetic benchmark; they do not establish general quality or real audience improvement.
- Model judging is subjective; candidate order is blinded and seeded, but the judge can still be biased.
- Writing and judging use different models through Mesh, but model-family and rubric biases remain.
- Voice profiles are extracted from five authored samples per fictional creator; this checks learned-voice wiring, not authentic personal fidelity.
- Paired bootstrap intervals are descriptive for these synthetic cases; a small, nonrandom benchmark and shared topics cannot establish population effects.
- Factual-care scores assess unsupported claims against supplied material, not external fact-checking. Mechanical checks measure explicit word and format constraints only.
- The five-dimension rubric adds factual care; its composite is not directly comparable to older four-dimension reports.
- Engagement tests use explicitly synthetic counts and show policy adaptation, not causal performance gains.
- No real publishing or live platform analytics were evaluated.
- Quality means include only successful scored pairs. Completion rate and failed-case artifacts are reported separately to expose selection bias.

## Manual review

Inspect the first two pairs in `results.json`, record observations here, and retain any disagreements with the judge. No human review has been claimed by this script.

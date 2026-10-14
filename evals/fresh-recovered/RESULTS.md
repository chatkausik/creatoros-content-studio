# CreatorOS evaluation results

Initial benchmark started: 2026-10-14T04:00:59.840760+00:00

Completed after recovery: 2026-10-14T19:23:36.986478+00:00

Mode: **live**. Authored synthetic benchmark with historical smoke cases and a fresh 24-pair suite. Fictional voices and simulated feedback; these are not audience outcomes.

- Completed pairs: 23/24 (95.8%)
- Text changed: 23/24
- Pairs passing all mechanical checks: 23/24
- Separately judged pairs: 23
- First-pass completion: 4/24; recovered pairs: 19
- Generation / judge model: `openai/gpt-5.1` / `openai/gpt-4.1`
- Explicit word/format constraints: 16 failures before; 15 after; 23 assessed pairs
- Returned generation model: gpt-5.1-2025-11-13; returned judge model: gpt-4.1-2025-04-14. Distinct model IDs do not establish statistical independence.
- Mean score among successfully judged pairs: 4.817 before → 4.913 after (1–5)
- Mean paired change: +0.096
- Wins / ties / losses: 8 / 12 / 3
- Score coverage: 23/24. Quality means are conditional on successful generation and judging; failed cases are not assigned zero or silently dropped from completion counts.
- Descriptive 95% paired-bootstrap interval: [-0.0522, +0.2435]. Small-sample flag: True.

| Dimension | Before | After | Paired change | 95% descriptive interval |
|---|---:|---:|---:|---|
| brief_fulfillment | 4.783 | 4.870 | +0.087 | [-0.1304, 0.3043] |
| specificity | 4.696 | 4.870 | +0.174 | [-0.0435, 0.3913] |
| clarity | 4.913 | 4.957 | +0.043 | [-0.087, 0.1739] |
| brand_fit | 4.696 | 4.870 | +0.174 | [-0.087, 0.4348] |
| factual_care | 5.000 | 5.000 | +0.000 | [0, 0] |

## Recovery accounting

This is a recovered evaluation, not an all-successful first pass. Successful cases and their existing judgments were retained unchanged; only failed operations were retried from frozen saved artifacts.

- Initial completion: 4/24 (16.7%)
- Completion after recovery: 23/24 (95.8%)
- Recovery attempts recorded: 1
- Original failures and sanitized diagnostics remain in each recovered item's `prior_attempts`; the initial summary and learning checks remain in `recovery`.

| Case | Brand | Changed | Before | After | Change |
|---|---|---|---:|---:|---:|
| fresh-privacy-brand-ada | brand-ada | False | — | — | — |
| fresh-privacy-brand-milo | brand-milo | True | 4.000 | 4.800 | +0.800 |
| fresh-accessibility-brand-ada | brand-ada | True | 5.000 | 5.000 | +0.000 |
| fresh-accessibility-brand-milo | brand-milo | True | 4.800 | 5.000 | +0.200 |
| fresh-rollback-brand-ada | brand-ada | True | 5.000 | 5.000 | +0.000 |
| fresh-rollback-brand-milo | brand-milo | True | 4.600 | 5.000 | +0.400 |
| fresh-batch-cost-brand-ada | brand-ada | True | 5.000 | 5.000 | +0.000 |
| fresh-batch-cost-brand-milo | brand-milo | True | 4.400 | 5.000 | +0.600 |
| fresh-timeouts-brand-ada | brand-ada | True | 5.000 | 4.600 | -0.400 |
| fresh-timeouts-brand-milo | brand-milo | True | 4.800 | 5.000 | +0.200 |
| fresh-versioning-brand-ada | brand-ada | True | 4.800 | 5.000 | +0.200 |
| fresh-versioning-brand-milo | brand-milo | True | 5.000 | 5.000 | +0.000 |
| fresh-stale-data-brand-ada | brand-ada | True | 5.000 | 4.400 | -0.600 |
| fresh-stale-data-brand-milo | brand-milo | True | 4.800 | 4.800 | +0.000 |
| fresh-duplicate-feedback-brand-ada | brand-ada | True | 5.000 | 5.000 | +0.000 |
| fresh-duplicate-feedback-brand-milo | brand-milo | True | 5.000 | 5.000 | +0.000 |
| fresh-dataset-consent-brand-ada | brand-ada | True | 5.000 | 5.000 | +0.000 |
| fresh-dataset-consent-brand-milo | brand-milo | True | 4.200 | 5.000 | +0.800 |
| fresh-multilingual-brand-ada | brand-ada | True | 5.000 | 5.000 | +0.000 |
| fresh-multilingual-brand-milo | brand-milo | True | 5.000 | 5.000 | +0.000 |
| fresh-error-logs-brand-ada | brand-ada | True | 4.400 | 5.000 | +0.600 |
| fresh-error-logs-brand-milo | brand-milo | True | 5.000 | 4.400 | -0.600 |
| fresh-uncertainty-brand-ada | brand-ada | True | 5.000 | 5.000 | +0.000 |
| fresh-uncertainty-brand-milo | brand-milo | True | 5.000 | 5.000 | +0.000 |

## Failed cases

Failed runs, partial drafts, and sanitized diagnostics are retained in `results.json`.

- fresh-privacy-brand-ada — strategist: GenerationFailure: Mesh returned invalid structured output twice (SelectedStrategy). The failed step can be retried.

## Learning checks

- feedback-reversal: PASS — Reversing supplied engagement changes the preferred hook; this tests policy behavior, not engagement causality.
- ablation-eval-safety: PASS — Matched brief and voice with feedback disabled/enabled. A separate blinded classifier receives only the actual opening sentences and must identify both selected hooks; fixture runs test policy wiring only.
- ablation-eval-feedback: PASS — Matched brief and voice with feedback disabled/enabled. A separate blinded classifier receives only the actual opening sentences and must identify both selected hooks; fixture runs test policy wiring only.

## Learned voices

Both generation profiles are extracted from the stored writing samples; source samples, their hash, and the extracted profiles are retained in `results.json`. These are authored fictional voices.

- brand-ada: mesh; 5 samples.
- brand-milo: mesh; 5 samples.

## Blind voice checks

Matched brief and hook with the correct, swapped, or neutral profile. A separate judge sees anonymous reference samples and the generated text, never the condition or target identity. Recognition rates are descriptive; six generations do not establish general voice fidelity.

| Profile condition | Target voice identified / scored | Operational failures |
|---|---:|---:|
| correct | 2/2 | 0 |
| swapped | 0/2 | 0 |
| neutral | 1/2 | 0 |

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
- This benchmark retains the generation schema used for its original attempt and recovery. Later scoped schema fixes are validated separately and do not rewrite this evidence.
- First-pass completion means one initial pipeline execution, including its bounded schema correction and editorial revisions, before any explicit recovery.

## Qualitative review

[Read the Codex-assisted review](../fresh/REVIEW.md). Codex-assisted inspection of two first-attempt pairs and one recovered regression, not an independent human assessment. Scores and generated text remain unchanged.

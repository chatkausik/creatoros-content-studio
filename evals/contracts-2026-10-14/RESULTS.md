# Brief-contract live validation

Completed: 2026-10-14T20:58:37.754853+00:00

Four new authored smoke cases were generated through Mesh using GPT-5.1 and fictional fixture voice profiles. No images, separate quality judge, profile extraction, recovery or rerolls were used. These are targeted functional checks, not a representative quality benchmark.

**Result: 3/4 generation runs completed; 2/4 final texts passed their agreed contracts.** One completed text remained over its word limit; the newsletter stopped at a structured editor-response failure. Both remained unapproved and required correction.

| Case | Original words | Final words | Final contract | Run outcome |
|---|---:|---:|---|---|
| retry-contract | 146 | 149 | Pass | complete |
| handoff-contract | 123 | 134 | Fail | complete |
| drift-sections | 165 | 150 | Pass | complete |
| newsletter-contract | 661 | 596 | Fail | failed |

## What the checks demonstrated

- The retry example started at 146 words, exceeded its limit during the first revision, and used the remaining repair attempt to finish at 149 words with exactly three bullets.
- The retrieval example moved from 165 to 150 words, retained both required headings, and passed its 120–160-word contract.
- The human-handoff example ended at 134 words against a 130-word limit after two revisions. Its deterministic failure remained visible despite model judgments; approval is blocked until a human correction satisfies the contract.
- The newsletter reduced from 661 to 596 words but still exceeded its 520-word contract. Its next editor response exceeded the 700-character instruction schema limit twice, so generation stopped with saved artifacts. That failure is preserved, not retried into a favorable result.

## Scope and reproducibility

Run `scripts/validate_contracts.py --plan-only --output data/evaluations/your-new-directory` to inspect the four cases and operation cap. Default execution uses authored fixtures; adding `--live` spends Mesh credits. Set `MESH_CHAT_MODEL=openai/gpt-5.1` to select the model used here. Always choose a new output directory.

Live generation is capped at four pipeline runs, at most two editorial revisions each, and a worst case of 56 Mesh requests including schema corrections. This is not a dollar cap. Returned response usage is retained in each run; response-less failures and provider billing may not be fully represented.

The two passing final contracts establish only these machine-checkable rules on these examples. They do not prove factual accuracy, improved writing, reliable compliance on unseen briefs, or audience uplift. The older benchmark and its 15 final constraint failures remain unchanged.

[Raw attempts, versions, reviews, manifests, usage, and checks](results.json). The app additionally has regression coverage for failed-contract approval blocking, manual correction, immutable versions, CSV import idempotency, and preregistered experiment assignments.

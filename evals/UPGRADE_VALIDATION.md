# Targeted upgrade validation

These checks verified fixes against observed failures. They are **targeted debugging verification, not independent quality benchmarks**. No results below replace the failed attempts or improve the fresh benchmark's completion or quality scores. All inference used Mesh; the newsletter uses the fictional Ada Chen profile in an isolated private store.

| Workflow | Preserved failure | Scoped change and verification |
| --- | --- | --- |
| Newsletter generation | The writer returned 772 words, then 889 after its bounded correction; both exceeded the unchanged 700-word limit. No image was requested. [First attempt](upgrade-smoke-first.json) | Newsletter-only instructions now target 500–550 words with section budgets; validation names the actual word count and required reduction. A new attempt with the same brief and model produced a 633-word draft and a substantive **630-word revision**, approved by the editor, with an initial image. [New configuration result](upgrade-smoke.json) |
| Image regeneration | The visual director returned prompts of 2,787 and 2,024 characters against a 2,000-character cap. The original image survived; no replacement image request was made. [Failure retained](upgrade-smoke.json) | VisualBrief now gives a 500–1,000-character target and count-aware correction feedback. One new visual-only attempt succeeded: one director call and one image request. The final image prompt was 1,748 characters including the appended no-text constraint. [Visual verification](visual-recovery.json) |
| Strategy explanation | `fresh-privacy-brand-ada` failed the strategist's 800-character explanation limit. Its failed benchmark result remains preserved. [Fresh benchmark](fresh/results.json) | Strategy.reason now targets 200–400 characters and reports actual over-limit length. One strategist-only call using the same frozen brief, profile, hook and policy returned a valid **413-character explanation**, preserving the hook. No pipeline or judge was rerun. [Targeted validation](strategy-validation.json) |

New run manifests also capture output-schema hashes alongside prompt hashes and model settings. Resume rejects a changed captured schema; older runs explicitly disclose uncaptured schema coverage instead of receiving invented historical hashes. Focused regression tests cover these checks, immutable feedback, image versions, editorial acknowledgement, timing, and platform isolation.

## Visual evidence

Both images were generated through Mesh and inspected by the assistant using `view_image`. This is an inspection of these assets, not automated image-quality scoring or human-user approval. No legible text was observed. The second image follows the requested calmer green/orange palette and makes the loop and stopping branch clearer. The images API did not return an actual-model identifier; the reports preserve that value as unknown and retain the requested model and usage.

| Initial image | Regenerated with feedback |
| --- | --- |
| ![Initial abstract key and pipeline illustration](assets/newsletter-initial.png) | ![Regenerated green loop with orange stopping branch](assets/newsletter-regenerated.png) |

The raw reports retain configurations, inputs, outputs, failures and available model provenance. These few selected cases establish neither a general reliability rate nor audience uplift.

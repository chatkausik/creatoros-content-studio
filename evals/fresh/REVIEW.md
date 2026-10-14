# Fresh benchmark qualitative review

Reviewer: Codex, October 14, 2026. This is an assistant-assisted inspection of two first-attempt pairs and one recovered regression, not an independent human assessment or a new model-judge score. It supplements the recorded benchmark and does not alter its scores or outputs. The first two cases completed before the connection interruption and remained unchanged during operational recovery.

## Privacy · Milo

The revision replaces a disconnected before/after example with three parallel bullets covering the example, retained field, and limitation. It removes an emoji and keeps the notebook metaphor and reflective closing. Those are observable editorial changes.

The final text still has **159 words against a 150-word maximum**; the original had 161. The judge's 5/5 brief-fulfillment score overlooks this. The judge also penalized the original for using an instructional structure even though the brief explicitly requested three bullets. A learned voice's preferences should not override a concrete requirement in the current brief.

The revision emphasizes lost context but drops the original's useful warning that small identifying clues can remain after redaction. It should not be described as an unqualified improvement in factual care or privacy guidance. The raw scores and both texts remain available in `results.json`.

## Accessibility · Ada

The revision explains nodes and edges in familiar terms and makes the reader's sketch test more concrete. It preserves the worked alt-text example and the practical emphasis on relationships.

However, the revision expands **153 words to 170**, moving farther beyond the 150-word maximum. The added claim that describing colors “fails completely” is too categorical for an example of incomplete alt text. The before/after model scores tie at 5/5 despite these limitations. A ceiling score is not reliable evidence that every requirement was met.

## Outdated sources · Ada · recovered regression

The model judge scored the revision 0.6 points lower, preferring the original's more explicit checks. In particular, “when the retrieved passages provide one” gives a more precise source boundary than the revision's “when one is available.” That loss of specificity is visible in the text and worth keeping in the report.

At the same time, the revision reduced the body from **154 to 134 words**, satisfying the 150-word maximum and retaining exactly three bullets, the old-manual example, and the uncertainty statement. The original fails the word limit. This case illustrates a real trade-off between concision and explicit detail, and a judge preference that does not fully account for a hard requirement. The negative score remains unchanged; it should be read alongside the improved constraint result, rather than hidden or rerun.

## Implications

- Report deterministic constraint failures alongside model scores; never summarize this experiment with the quality average alone.
- Treat explicit brief requirements as higher priority than inferred stylistic preferences.
- Word limits supplied in free-form briefs are currently evaluated but are not enforced by the platform schema. The LinkedIn 3,000-character ceiling and newsletter 400–700-word range are enforced separately. A future release should expose structured per-brief limits and validate them during drafting and revision.
- Keep the original failures, connection-interruption record, and any operational recovery report. Repeating completed outputs until they satisfy the judge would invalidate the comparison.

The small synthetic benchmark measures generated text and model judgments. It does not establish higher real-world engagement or prize eligibility.

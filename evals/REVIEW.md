# Qualitative spot review

Reviewer: Codex, agent-assisted inspection of saved outputs on 2026-10-14. This is not an independent human evaluation. The original model judgments and every generated draft remain unchanged in `results.json`.

## Retrieval / Ada

The revision adds a note explaining why a retrieved result is wrong and a concrete expectation for the EU-policy example. Those are inspectable changes that support the increase in specificity. The before/after pair is preserved as `eval-retrieval-brand-ada`.

The judge's perfect clarity score is generous: the draft grows from 197 to 317 words, beyond the writer's usual 120–220-word guidance. The added phrase about seeing a broken contract “in seconds” also implies a speed that the benchmark did not measure. The extra detail has value, but the shorter original is easier to scan. A human should review concision and such claims before publication.

## Human approval / Ada

The revision makes the example more implementable by adding allowed-action checks, amount limits, required fields, and explicit approval logging. These concrete additions support the judge's specificity improvement in `eval-safety-brand-ada`.

The revision also adds the agent's self-reported confidence. This benchmark did not validate its calibration or whether showing it helps reviewers make better decisions. That addition is not itself evidence of improved safety, even though the judge rewarded the extra detail. The post grows from 195 to 240 words.

## Retained regression

`eval-safety-brand-milo` falls from 5.0 to 4.75. The judge found the revised benefit-focused sentence less consistent with Milo's reflective voice. Both versions have 187 words, so this is not simply a length effect. The regression is retained, not rerolled or removed.

## Interpretation

The eight-pair mean rises from 4.562 to 4.938 after recovery, but individual edits can reduce voice fit and longer text can receive inflated model scores. Four initial generation failures were caused by a 500-character evidence-note bound; their artifacts were preserved and resumed after widening that audit field to 1,200 characters. All eight final pairs are scored, while the original 4/8 completion rate remains visible.

The two feedback ablations support the narrow claim that the selected opening policy reaches the prose. Their engagement counts are synthetic and do not establish an engagement uplift. Human approval remains part of the publishing workflow.

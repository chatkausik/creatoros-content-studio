# CreatorOS design decisions

## Make adaptation inspectable

The central interaction is a comparison: the original strategy, the new performance evidence, the updated preference, and the resulting next draft. Storing more metrics alone would not close the loop. CreatorOS applies a narrow policy to the next run and exposes the evidence that selected it.

The first learning variable is the opening style. A fixed three-option policy is inexpensive, reproducible, and easy to inspect. Its observations are not a randomized trial: topic, timing, audience changes, and selection effects can explain engagement differences. The interface therefore labels sparse findings as early signals and reports counts alongside rates.

Voice remains separate from performance preferences. A brand profile derives from multiple supplied samples. Strategy learning chooses among allowed openings while the writer retains that profile. The run freezes both inputs, preventing later edits from changing the explanation of earlier output.

## Durable artifacts and bounded work

FastAPI owns the local application lifecycle. SQLAlchemy manages a SQLite document store for explicit domain records. LangGraph coordinates named agent steps with persisted checkpoints. The frontend reads saved state rather than keeping the only copy of in-flight output.

Each run retains its strategy, original text, reviews, revisions, image brief, and image result. A revision cites the editor requests it addresses. Decision events link content to input samples and feedback observations. A refresh can recover progress; a retry should continue unfinished work without discarding completed paid artifacts.

The editor loop is bounded to control latency and spending. A post with unresolved issues remains reviewable; a loop completion is not an assertion of factual accuracy. Writers must avoid invented personal experiences and unsupported statistics. Users approve publication.

External APIs cannot provide a distributed exactly-once guarantee: a process crash after a provider completes work but before the application saves the result can still incur a repeated request. Persisted steps and request caching reduce that risk but do not eliminate it.

## Data provenance

| Data | Source | Treatment |
|---|---|---|
| Seeded brands and writing samples | Demonstration fixtures | Clearly labeled, never presented as user writing |
| Seeded engagement | Synthetic fixtures | Kept in the simulated feedback cohort |
| Imported writing | User supplied or read from the user's requested profile | Stored privately with source attribution and used to derive a profile |
| Entered performance | User supplied | Scoped by brand, observation window, and provenance |
| Authenticated LinkedIn card metrics | Read-only creator profile inspection | Retained as cumulative/unspecified-window reference data; excluded from 24-hour/7-day cohorts |
| Live text and images | Mesh | Model/prompt metadata and generated outputs are retained |
| Fixture text | Deterministic local examples | No claim of live AI generation or quality measurement |

Feedback upserts identify the post, provenance, and observation window so editing an observation does not count it twice. Learning snapshots are immutable historical records. Missing/zero impressions do not produce a rate. Observation windows are never pooled together.

The working creator profile uses eight original LinkedIn posts. Two reposts were excluded because their substantial text belonged to other authors. The source capture preserves exact post text, canonical links, displayed dates, and only explicitly displayed counts. These private local files and the generated brand profile are not committed. The public demonstration and evaluation use authored fixtures so a fresh checkout is reproducible without someone else's account.

## Evaluation

Eight paired cases cover four new technical briefs and two distinct demonstration profiles. Mechanical checks ask whether an original exists, content changed, reviews contain requests, and revisions link to requests. These checks validate the pipeline; they do not measure writing quality.

Live evaluation uses a separate Mesh judge prompt with an anchored 1–5 rubric for brief fulfillment, specificity, clarity, and brand fit. It hides candidate stage labels and randomizes their order. The report retains raw judgments, complete text, all scores, and regressions. Failed generation artifacts and safe schema diagnostics also survive isolated-store cleanup. Raw rejected output is kept in ignored local diagnostics. The same base model may generate and judge output, so correlation and preference bias remain limitations.

Feedback evaluation has two parts: reversing synthetic metric rankings must reverse the selected preference, and matched briefs with learning disabled/enabled expose their selected hooks and final text. Each ablation branch starts from equivalent fresh data and the same selection sequence. A separate blinded classifier receives only the first visible sentence from each output, with no intended-hook metadata or later prose. It must quote the sentence exactly and classify the actual opening correctly. This separates policy selection from its execution in prose; it still does not prove higher future engagement.

The initial live benchmark completed eight pairs with scores of 4.469 before and 4.906 after, seven wins, one tie, and no losses. Stricter checks then surfaced incomplete generations and misleading full-post opening classifications. Both historical reports remain in `evals/history/`. Current reports disclose completion rate alongside quality means conditional on successful cases. Earlier favorable numbers are not a substitute for validating later code. Two human spot-checks are recommended before presenting quality claims.

## Deployment boundary

This is a single-user local application. It has no external publishing credential, authentication layer, distributed job coordinator, or production hosting claim. The scheduler marks posts ready; it does not publish them. UTC storage avoids ambiguous persistence, and the UI supplies the user's local timezone.

All AI access is centralized behind a Mesh adapter. The server reads keys from the environment. The browser receives neither credentials nor provider authorization headers. Generated image responses are normalized into local files so the queue does not depend on temporary provider URLs.

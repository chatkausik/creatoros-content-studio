# CreatorOS design decisions

## Make adaptation inspectable

The central interaction is a comparison: the original strategy, the new performance evidence, the updated preference, and the resulting next draft. Storing more metrics alone would not close the loop. CreatorOS applies a narrow policy to the next run and exposes the evidence that selected it.

The first learning variable is the opening style. A fixed three-option policy is inexpensive, reproducible, and easy to inspect. Policy v2 requires three posts and 300 impressions per opening, then compares descriptive 90% post-level bootstrap ranges (500 resamples). Overlapping ranges, ties, or insufficient exposure keep the policy exploring. This is a heuristic, not a randomized trial or significance guarantee: topic, timing, audience changes, and selection effects can explain engagement differences. Cohorts separate brand, platform, provenance, and measurement window.

Voice remains separate from performance preferences. A brand profile derives from multiple supplied samples. Strategy learning chooses among allowed openings while the writer retains that profile. The run freezes both inputs, preventing later edits from changing the explanation of earlier output.

## Durable artifacts and bounded work

FastAPI owns the local application lifecycle. SQLAlchemy manages a SQLite document store for explicit domain records. LangGraph coordinates named agent steps with persisted checkpoints. The frontend reads saved state rather than keeping the only copy of in-flight output.

Each run retains its strategy, original text, reviews, revisions, image brief, and image result. New manifests freeze requested models, prompt hashes, output-schema hashes, generation settings and platform; resume rejects incompatible captured prompts or schemas before inference. Legacy manifests disclose inferred fields and uncaptured schema coverage. Separate image variants and human-edit reviews are new actions with their own current manifests, rather than silently changing an old text run. Interrupted image requests retain their original manifest and mode. Invalid image payloads are invalidated; transient downloads reuse the paid response. Explicit regeneration starts a new request and bypasses cache.

Human edits create versions and mark earlier reviews/visuals stale. The UI shows the latest review and full history, provides a recheck action, and requires explicit acknowledgement before approving unresolved concerns. Active-work guards prevent conflicting edits, approval, scheduling and publication. Async completion rechecks the current post before saving; an old run cannot resume over later human or publishing decisions. Image selection retains version history and invalidates prior approval.

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

Feedback upserts identify the post, provenance, and observation window so editing an observation does not count it twice. Corrections also append immutable revisions. New learning snapshots embed the exact eligible observations and post openings; older aggregate-only records are explicitly labeled rather than fabricated from current data. Exact repeated requests preserve the same revision. Missing/zero impressions do not produce a rate. Manual observations need a consistent measurement time or declared interval; unknown/cumulative windows remain excluded. Data-entry time is separate from measurement time.

The working creator profile uses eight original LinkedIn posts. Two reposts were excluded because their substantial text belonged to other authors. The source capture preserves exact post text, canonical links, displayed dates, and only explicitly displayed counts. These private local files and the generated brand profile are not committed. The public demonstration and evaluation use authored fixtures so a fresh checkout is reproducible without someone else's account.

## Evaluation

The smoke suite has eight paired cases; the fresh suite has 12 unseen briefs across two distinct voices, yielding 24 pairs. Both profiles can be learned through Mesh from five authored samples each. Mechanical checks ask whether an original exists, content changed, reviews contain requests, and revisions link to requests. Explicit word, character, bullet, and formatting limits are checked separately from model scores. These checks validate observable behavior; they do not establish factual accuracy.

Live evaluation uses a separate Mesh judge prompt with an anchored 1–5 rubric for brief fulfillment, specificity, clarity, brand fit, and factual care. The fresh benchmark selects GPT-4.1 to judge GPT-5.1 output, hides candidate stage labels, and randomizes their order. Different models still share possible preference biases. Reports retain raw judgments, complete text, all scores, regressions, first-attempt completion, and descriptive paired bootstrap ranges. The five-dimension score is not directly comparable with earlier four-dimension results. Factual-care scores reflect model judgment, not external fact-checking.

Six additional voice branches compare correct, swapped, and neutral profiles for both fictional voices. A blinded classifier receives anonymous reference samples and prose, without the intended condition. This tests whether the profile affects recognizable style rather than merely changing metadata. It does not certify fidelity to a real creator.

Benchmark progress is saved atomically after completed operations. Private persistent workspaces retain pipeline artifacts, failures, raw diagnostics, and paid-response caches for interruption recovery. A run cap and a preview of worst-case request counts bound work; they are not a dollar budget. Resume checks the saved manifest and rejects changed prompts/models. Completed quality failures are retained, rather than regenerated until they pass.

Feedback evaluation has two parts: reversing synthetic metric rankings must reverse the selected preference, and matched briefs with learning disabled/enabled expose their selected hooks and final text. Each ablation branch starts from equivalent fresh data and the same selection sequence. A separate blinded classifier receives only the first visible sentence from each output, with no intended-hook metadata or later prose. It must quote the sentence exactly and classify the actual opening correctly. This separates policy selection from its execution in prose; it still does not prove higher future engagement.

The initial live benchmark completed eight pairs with scores of 4.469 before and 4.906 after, seven wins, one tie, and no losses. Stricter checks then surfaced incomplete generations and misleading full-post opening classifications. Both historical reports remain in `evals/history/`. Current reports disclose completion rate alongside quality means conditional on successful cases. Earlier favorable numbers are not a substitute for validating later code. Two human spot-checks are recommended before presenting quality claims.

The fresh benchmark and transport-only recovery scored 23 of 24 pairs: 4.817 before and 4.913 after, with three regressions and a paired interval including zero. Fifteen final texts missed at least one exact brief constraint. Both controlled opening comparisons passed. These results support a functioning adaptive loop, not a general quality or engagement guarantee. Subsequent newsletter, visual and strategy schema-guidance fixes have separate [targeted verification](../evals/UPGRADE_VALIDATION.md); the original benchmark artifacts remain unchanged. The [Codex-assisted inspection](../evals/fresh/REVIEW.md) records disagreements with the model judge and is not independent human review.

## Platform adaptation

LinkedIn uses a plain-text post with a 3,000-character maximum. Newsletter generation uses a subject, 400–700 words, developed sections, an example and an exercise. Platform-specific schemas and agent context validate the distinction. Learning stays scoped to the platform. Newsletter copy/Markdown export is available; no email sending service is implied.

## Deployment boundary

This is a single-user local application. It has no external publishing credential, authentication layer, distributed job coordinator, or production hosting claim. The scheduler marks posts ready; it does not publish them. UTC storage avoids ambiguous persistence, and the UI supplies the user's local timezone.

All AI access is centralized behind a Mesh adapter. The server reads keys from the environment. The browser receives neither credentials nor provider authorization headers. Generated image responses are normalized into local files so the queue does not depend on temporary provider URLs.

# Submission evidence and final handoff

The challenge's source requirements are in [requirement.md](../requirement.md). The public repository is [chatkausik/creatoros-content-studio](https://github.com/chatkausik/creatoros-content-studio). Both required Actions secret names are configured, and the project's build/regression workflow has passed.

**CI status:** the registration token was corrected from the authenticated Agent Arena dashboard. [Organizer attempt 2](https://github.com/chatkausik/creatoros-content-studio/actions/runs/38504352208/attempts/2) passes all four critical checks and all three advisory checks. Result recording remains blocked with HTTP 403 because submissions open **October 14, 2026 at 11:30 PM Eastern (October 15 at 03:30 UTC)**. The organizer has not yet recorded an eligible result.

The separate [opening retry workflow](../.github/workflows/agent-arena-opening-retry.yml) schedules a rerun at 03:43 UTC on October 15, with 04:43 and 05:43 UTC fallbacks. GitHub may delay scheduled jobs. It selects the official push run for the current `main` commit, waits for its actual result, and disables itself only after success (or after the submission window closes). It requires no Mesh or submission secrets. The organizer workflow remains byte-for-byte unchanged. A manual run before opening only reports that it is waiting; it does not establish eligibility.

The final live report scores all eight pairs after artifact recovery, preserves the original four first-attempt failures, and passes both actual-opening ablations. Read the [qualitative review](../evals/REVIEW.md) alongside the numbers.

| Requirement | Implemented evidence |
|---|---|
| Every AI call goes through Mesh | Central Mesh adapter, server-side configuration, and gateway validation; text, images, profiles, and evaluation judges share it |
| At least three distinct agents | Separate strategist, writer, editor, and visual prompts in a named LangGraph pipeline |
| Genuine editorial refinement | Original text, concrete requests, substantive revisions, linked changes, and preserved decision events |
| Learned brand voice | Multi-sample profile extraction with grounded quotes; two reproducible fixture voices and eight authentic samples in private local data |
| Matching visuals and scheduling | Mesh image generation, stored local assets, approval, timezone-aware queue, restart recovery, and manual publication confirmation |
| Performance learning | Versioned hook preferences from scoped observations, exploration, evidence links, and subsequent run consumption |
| Audit trail | Content-linked strategy, editorial, visual, scheduling, publication, and learning decisions |
| Self-evaluation with numbers | [Current report](../evals/RESULTS.md), [initial report](../evals/history/initial/RESULTS.md), [first strict report](../evals/history/strict-first/RESULTS.md), raw cases, and reproducible evaluation script |
| Submission package | Source, manifests, [README](../README.md), [design note](DESIGN.md), unchanged organizer workflow, and separate regression-test workflow |
| Optional demo | [75-second captioned screenshot walkthrough](demo.mp4), with fixture provenance disclosed; no deployed URL is claimed |

## Before the final commit

1. Finish the corrected live evaluation. Inspect its completion rate, failed-case diagnostics, and both actual-opening ablations. Resolve or disclose failures; do not present the earlier 7-win result as a pass for later code.
2. Inspect at least two saved draft/revision pairs and record the reviewer and observations. Keep the original and strict historical reports.
3. Run the frontend build, regression suite, and local submission preflight using the README commands. A fixture rerun should use `--output /tmp/creatoros-fixture-evaluation` so it does not replace live evidence.
4. Review staged paths before committing. Include source, `frontend/package-lock.json`, direct dependency constraints, reports, and demo artifacts. Keep `.env`, `data/`, SQLite files, generated caches, and the virtual environment excluded.

## Publish the submission package

1. The **public GitHub repository** is published and attached as `origin`: [chatkausik/creatoros-content-studio](https://github.com/chatkausik/creatoros-content-studio).
2. Add repository Actions secrets named exactly `MESH_API_KEY` and `SUBMISSION_TOKEN`. Enter them in GitHub's secret form or an interactive secret command; do not put values in source or command history. [GitHub secret documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets)
3. Push the reviewed submission commit. Preserve `.github/workflows/agent-arena-2026-checks.yml` unchanged, including its OIDC permissions and audience.
4. Verify the **Agent Arena Checks** run and **CreatorOS Tests** run for that exact commit, then verify the matching commit appears on the challenge dashboard.
5. Submit the public repository URL and, if accepted by the submission form, a hosted copy of the short demo. A deployed application URL is optional for this challenge.

CreatorOS's own CI does not use AI credentials or spend Mesh credits. The organizer's workflow performs its required key-validity check using the repository secret. Local tests alone do not establish remote eligibility.

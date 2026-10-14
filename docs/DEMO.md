# Demo walkthrough and recording storyboard

[Watch the 75-second captioned walkthrough](demo.mp4). The video is a sequence of screenshots captured from the actual application using labeled demonstration fixtures. It is not a real-time recording of agent execution or evidence of published LinkedIn content. The live benchmark reports provide independent AI-run evidence.

Still images: [Studio](screenshots/studio.png), [voice profile](screenshots/voice.png), [editor comparison](screenshots/editor.png), [queue](screenshots/queue.png), [learning](screenshots/learning.png), [next post](screenshots/next-post.png), and [decision trail](screenshots/decisions.png).

The following three-minute storyboard is available for a longer live recording.

Use your real multi-sample brand and authentic manually entered metrics when available. Otherwise keep the application's demo and simulated labels visible. Use a recorded successful run if latency makes a fresh run impractical, and identify it as recorded. Do not imply that a local demo was published on LinkedIn.

The local creator profile has eight authentic source-attributed samples. Its captured LinkedIn counts have an unspecified cumulative window; do not relabel them as first-24-hour or first-7-day observations for the demonstration. Use the explicit simulated cohort to demonstrate a reproducible preference change until comparable real observations are available.

| Time | On screen | Suggested narration |
|---|---|---|
| 0:00–0:25 | Brand samples, extracted profile, evidence excerpts | “CreatorOS keeps the writing anchored to these samples while learning which openings appear to resonate.” |
| 0:25–1:05 | Brief, named agent steps, original/revision comparison | “The strategist chooses an angle. The editor requests specific changes, and the writer's revision preserves a visible trail.” |
| 1:05–1:25 | Matching image, approval, scheduled queue | “The visual follows the final post. The queue persists the scheduled time and marks it ready for manual publication.” |
| 1:25–2:10 | Published-post metrics, observation window, new snapshot | “These observations produce a new opening preference. The counts and evidence remain visible, with an early-signal label.” |
| 2:10–2:40 | Next strategy and draft compared with prior run | “This run consumed the updated preference and changed its opening while keeping the same voice profile.” |
| 2:40–3:00 | Evaluation summary and case detail | “We tested the loop reproducibly. These are the actual reported results, including limitations and any regressions.” |

## Before recording

- Build the frontend and verify that a clean local startup works.
- Check whether the current evaluation is fixture or live. Claim editorial score improvement only when actual independent live scores support it.
- Keep synthetic provenance visible and avoid displaying `.env`, keys, submission tokens, or private account information.
- Prepare one successful text/image run and one feedback update that visibly changes the policy.
- Keep the original draft, editor requests, revised draft, supporting observation, and evaluation case one click away.
- Test scheduling with a near-future timestamp, then show the saved queue after refresh.

## Suggested closing claim

“CreatorOS preserves the evidence of each editorial change and demonstrates that performance feedback changes the strategy used by later posts.”

Only add a numerical quality-improvement claim after checking the current live evaluation report. An eight-pair model evaluation does not establish higher audience engagement.

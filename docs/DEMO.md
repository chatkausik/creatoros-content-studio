# CreatorOS demo walkthrough

[Watch the 90-second captioned walkthrough](demo.mp4). This is a sequence of actual application screenshots, assembled with captions. It is not a real-time recording of agent execution. Every featured profile, sample, draft, image and feedback observation belongs to the fictional Ada Chen demonstration workspace. No content was published to an external platform for this walkthrough.

The demo mode uses deterministic text and editorial fixtures and illustrative SVG images. Its scores do not measure live AI quality. The simulated engagement figures are authored inputs for exercising the learning policy, not audience outcomes. Live evaluation results, failures and limitations are reported separately in the [fresh benchmark](../evals/fresh/RESULTS.md) and [qualitative inspection](../evals/fresh/REVIEW.md); different judge and writing models can still share biases.

## Captioned sequence

| Time | Screen | What the frame shows |
|---|---|---|
| 0:00–0:09 | [Studio](screenshots/studio.png) | A brief, platform selector, demo label and the strategist, writer, editor and visual stages. |
| 0:09–0:17 | [Brand voice](screenshots/voice.png) | The fictional profile beside its authored source samples. |
| 0:17–0:28 | [Editor comparison](screenshots/editor.png) | Saved draft changes and the latest unresolved editorial request after a human edit. |
| 0:28–0:37 | [Visual direction](screenshots/visuals.png) | Feedback for a new visual, with preserved versions available behind the dialog. |
| 0:37–0:45 | [Publishing queue](screenshots/queue.png) | One due item and one scheduled reminder; the creator handles publication. |
| 0:45–0:56 | [Learning](screenshots/learning.png) | Comparable simulated observations, uncertainty ranges and an early preference. |
| 0:56–1:06 | [Frozen evidence](screenshots/evidence.png) | Snapshot v4, its thresholds and an expanded observation with the actual opening, counts and window. |
| 1:06–1:18 | [A later draft](screenshots/next-post.png) | A problem-first opening generated using snapshot v4. The policy also preserves exploration. |
| 1:18–1:30 | [Newsletter](screenshots/newsletter.png) | A subject and longer narrative with sections and a worked hypothetical example. Text and Markdown exports support manual publishing. |

## Reading the learning demonstration

The earlier [snapshot v3](screenshots/learning-before.png) was inconclusive: the problem-first range overlapped the outcome-first range. Two simulated feedback records were then changed to create a consistent demonstration cohort. Snapshot v4 preserves nine observation records across three opening styles, with three posts and 6,000 impressions per style. Its problem-first average is 61.7 comments plus reposts per 1,000 impressions. This number is an authored fixture result, not a measured improvement.

The [actual opening chain](screenshots/learning-chain.png) intentionally retains the first draft generated with v4: it uses an outcome-first opening because every fourth usable draft explores. The following draft uses the preferred problem-first opening shown in the video. Both consume the same saved policy. Earlier snapshots and their evidence remain available when later metrics change; the UI can open the exact snapshot used by a selected draft.

The displayed 90% ranges are descriptive post-level bootstrap ranges. They do not establish causality or higher audience engagement. Real and simulated observations, platforms and observation windows remain separate.

## Additional close-ups

- [Manual editing](screenshots/manual-edit.png): a human revision saves a new version and clears its approval.
- [Approval acknowledgement](screenshots/approval.png): unresolved editorial concerns require an explicit creator decision.
- [Saved visuals](screenshots/visual-gallery.png): three preserved versions, their feedback and the selected visual. Demo regeneration can produce the same SVG composition; live image regeneration is a paid Mesh request.
- [Decision trail on mobile](screenshots/decisions.png): readable strategy and editor decisions with linked evidence.
- [Newsletter on mobile](screenshots/mobile.png): a 390-pixel preview with no horizontal overflow.

## Rebuilding the walkthrough

Capture the application through a browser using only clearly labeled fictional records, then run:

```sh
python3 scripts/build_demo.py
```

The script requires `ffmpeg` and uses the nine screenshots listed in its `SCENES` array. It produces `docs/demo.mp4` at 1600 × 1000, 24 frames per second, with a 90-second duration. There is no audio track. Keep the screenshot-sequence and fixture disclosures when sharing the video. Local scheduling is a reminder workflow; publishing to LinkedIn or a newsletter platform is manual.

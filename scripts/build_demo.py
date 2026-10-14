#!/usr/bin/env python3
"""Assemble a captioned walkthrough from actual browser captures (requires ffmpeg).

This is a screenshot walkthrough, not a real-time screen recording. Capture the
application through the browser before running this optional packaging script.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENES = [
    ("studio", 9, "CreatorOS | A studio that keeps its evidence",
     "Strategist, writer, editor and visual stages share a persistent creative workflow.\nActual app screenshots; all featured brands, posts and feedback are demonstration fixtures."),
    ("voice", 8, "A voice grounded in writing samples",
     "Inspect the profile, source samples and supporting excerpts before drafting.\nThis fictional brand uses a demo profile; live AI extraction and generation use Mesh."),
    ("editor", 11, "Review the latest version, not yesterday's scores",
     "Human edits create new versions. The final review keeps unresolved requests visible.\nA creator can recheck the draft or explicitly acknowledge concerns before approval."),
    ("visuals", 9, "Keep the visual that fits",
     "Regenerate with feedback and select any preserved image version.\nThese are labeled SVG demo fixtures; live image generation uses paid Mesh requests."),
    ("queue", 8, "Plan the handoff to publication",
     "Approve a draft, attach a visual and save a publishing reminder.\nScheduling is local; publication on LinkedIn or a newsletter platform remains manual."),
    ("learning", 11, "Enough evidence to change direction",
     "Comparable simulated observations inform an opening preference, with uncertainty visible.\nReal and simulated metrics stay separate; weak or overlapping evidence keeps exploration active."),
    ("evidence", 10, "Freeze the evidence behind the decision",
     "Each snapshot preserves exact observation revisions, counts, source and window.\nCorrecting today's metrics does not rewrite an earlier learning decision."),
    ("next-post", 12, "Follow the policy into actual prose",
     "A saved policy guides the actual opening; every fourth usable draft still explores.\nThese fixture drafts demonstrate policy behavior, not measured audience uplift."),
    ("newsletter", 12, "A second format with room to explain",
     "Newsletter drafts have a subject, longer sections and a worked example.\nCopy or export text and Markdown; use the saved evaluation reports to inspect quality limits."),
]


def main():
    if not shutil.which("ffmpeg"):
        raise SystemExit("Install ffmpeg to create the optional demo video.")
    target = ROOT / "docs/demo.mp4"
    font = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
    font_opt = f"fontfile='{font}':" if font.exists() else "font='sans-serif':"
    with tempfile.TemporaryDirectory(prefix="creatoros-demo-") as directory:
        work = Path(directory)
        for index, (name, seconds, title, caption) in enumerate(SCENES):
            source = ROOT / f"docs/screenshots/{name}.png"
            if not source.exists():
                raise SystemExit(f"Missing browser capture: {source}")
            heading = work / f"heading-{index}.txt"
            body = work / f"caption-{index}.txt"
            second_line = work / f"caption-second-{index}.txt"
            heading.write_text(title)
            first, second = caption.split("\n", 1)
            body.write_text(first)
            second_line.write_text(second)
            filters = (
                "scale=1600:850:force_original_aspect_ratio=decrease,"
                "pad=1600:1000:(ow-iw)/2:0:color=0xF6F5F0,"
                f"drawtext={font_opt}textfile='{heading}':expansion=none:fontsize=29:fontcolor=0x284B40:x=36:y=871,"
                f"drawtext={font_opt}textfile='{body}':expansion=none:fontsize=22:fontcolor=0x343A34:x=36:y=918,"
                f"drawtext={font_opt}textfile='{second_line}':expansion=none:fontsize=22:fontcolor=0x343A34:x=36:y=952"
            )
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-loop", "1",
                            "-i", str(source), "-t", str(seconds), "-vf", filters,
                            "-r", "24", "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                            "-pix_fmt", "yuv420p", str(work / f"scene-{index}.mp4")], check=True)
        manifest = work / "scenes.txt"
        manifest.write_text("\n".join(f"file '{work / f'scene-{i}.mp4'}'" for i in range(len(SCENES))))
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                        "-i", str(manifest), "-c", "copy", "-movflags", "+faststart", str(target)], check=True)
    print(f"Saved {target} ({sum(scene[1] for scene in SCENES)} seconds)")


if __name__ == "__main__":
    main()

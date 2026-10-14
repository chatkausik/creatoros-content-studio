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
    ("studio", 9, "CreatorOS | Content that compounds",
     "A working content studio with distinct strategist, writer, editor and visual agents.\nActual app captures; this walkthrough uses clearly labeled demonstration data."),
    ("voice", 9, "One creator. A consistent voice.",
     "Multiple writing samples ground a reusable voice profile.\nLive extraction and every AI generation call run through Mesh."),
    ("editor", 12, "The editor changes the writing",
     "Original and revised drafts are saved, with concrete critique and visible changes.\nDemo fixtures illustrate the workflow; the repository also contains live evaluations."),
    ("queue", 9, "A persistent publishing queue",
     "Approve content, attach its visual, and schedule a local reminder.\nWhen it is due, publish on LinkedIn yourself and confirm it in the studio."),
    ("learning", 14, "Why the next post changes",
     "Simulated feedback changes the preferred opening from outcome-first to problem-first.\nReal and simulated metrics stay separate, with matching observation windows."),
    ("next-post", 12, "The decision reaches the actual prose",
     "The next draft opens with a concrete problem and records learning version 2.\nEvery fourth selection explores another opening; associations are not causal claims."),
    ("decisions", 10, "Follow every decision back to evidence",
     "Inspect the selected strategy, requested edits, saved revisions and feedback sources.\nRun locally, bring your own voice, and measure what improves."),
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

#!/usr/bin/env python3
"""Run a real Mesh content + optional image check with a saved creator profile."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.creatoros.config import load_settings
from backend.creatoros.pipeline import generate_visual, run_pipeline
from backend.creatoros.service import create_run
from backend.creatoros.store import Store


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brand", default="brand-kausik")
    parser.add_argument("--image", action="store_true")
    args = parser.parse_args()
    settings = load_settings()
    store = Store(settings.data_dir)
    from backend.creatoros.prompts import PROMPT_VERSION
    brand = store.get("brands", args.brand)
    if not brand or not brand.get("profile"):
        print("Import samples and learn the brand profile before running this check.", file=sys.stderr)
        sys.exit(1)
    marker_id = f"live-smoke:{args.brand}:{brand['profile_version']}:{PROMPT_VERSION}:{settings.chat_model}"
    marker = store.get("meta", marker_id)
    if marker:
        run = store.get("runs", marker["run_id"])
    else:
        run = create_run(store, settings, {
            "brand_id": args.brand,
            "brief": "Write a LinkedIn post for AI engineers about why evaluation should be a feedback loop, not a final checkbox. Explain a practical three-step workflow: capture a failure, make one change, and rerun the same cases. Keep it grounded: do not invent statistics, personal achievements, or customer stories. End with a specific question for other builders.",
            "mode": "live", "use_learning": True, "feedback_source": "manual", "window": "24h", "generate_image": False,
        })
        store.put("meta", {"id": marker_id, "run_id": run["id"]})
    await run_pipeline(run["id"], store, settings)
    run = store.get("runs", run["id"])
    post = store.get("posts", run["post_id"])
    if run["status"] != "complete":
        print(json.dumps({"status": run["status"], "stage": run["stage"], "error": run.get("error")}, indent=2))
        sys.exit(1)
    if args.image and post.get("image_source") != "mesh":
        result = await generate_visual(post, settings, "live")
        post = store.patch("posts", post["id"], {
            "image_url": result["image_url"], "image_prompt": result["image_prompt"],
            "image_model": result["model"], "image_source": result["source"],
        })
        store.add_event(post["id"], "visual", "Generated a matching visual through Mesh",
                        result.get("reason", result["image_prompt"]), event_id=f"image:{post['id']}:live")
    print(json.dumps({"run_id": run["id"], "post_id": post["id"], "status": run["status"],
                      "post_status": post["status"], "model": settings.chat_model,
                      "draft_versions": len(post.get("versions", [])), "reviews": len(post.get("reviews", [])),
                      "characters": len(post["content"]), "image_url": post.get("image_url"),
                      "image_source": post.get("image_source"), "usage": run.get("usage", [])}, indent=2))
    store.close()


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""Four bounded contract checks; fixture by default, --live spends Mesh credits."""
import argparse
import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.creatoros.config import load_settings
from backend.creatoros.contracts import check_contract
from backend.creatoros.fixtures import seed_demo
from backend.creatoros.pipeline import run_pipeline
from backend.creatoros.service import create_run
from backend.creatoros.store import Store, utcnow

CASES = [
    {"id": "retry-contract", "brand_id": "brand-ada", "platform": "linkedin",
     "brief": "Explain why retrying a payment request needs an idempotency key. Use an explicitly hypothetical example, exactly three bullets, 120–150 words, no hashtags. Do not invent results or personal experience.",
     "contract": {"min_words": 120, "max_words": 150, "min_bullets": 3, "max_bullets": 3, "max_hashtags": 0, "plain_text": True}},
    {"id": "handoff-contract", "brand_id": "brand-milo", "platform": "linkedin",
     "brief": "Explain a graceful human handoff when an assistant lacks enough context. Use 100–130 words, no bullets, no hashtags, and one hypothetical example. Avoid unsupported statistics and invented experience.",
     "contract": {"min_words": 100, "max_words": 130, "max_bullets": 0, "max_hashtags": 0, "plain_text": True}},
    {"id": "drift-sections", "brand_id": "brand-ada", "platform": "linkedin",
     "brief": "Describe a simple check for changing retrieval results. Write 120–160 words with plain section headings 'Try this' and 'Limits', each on its own line. Include a hypothetical example and a limitation. No hashtags or invented measurements.",
     "contract": {"min_words": 120, "max_words": 160, "required_sections": ["Try this", "Limits"], "max_hashtags": 0, "plain_text": True}},
    {"id": "newsletter-contract", "brand_id": "brand-milo", "platform": "newsletter",
     "brief": "Write a practical newsletter on reviewing tool permissions before an agent workflow runs. Use 450–520 words and plain section headings 'A worked example', 'Try this', and 'Limits'. Develop a hypothetical example, an exercise and the trade-offs. No hashtags or invented measured results.",
     "contract": {"min_words": 450, "max_words": 520, "required_sections": ["A worked example", "Try this", "Limits"], "max_hashtags": 0, "plain_text": True}},
]


async def main(args):
    plan = {"cases": CASES, "pipeline_runs": len(CASES), "max_revisions_per_run": 2,
            "max_mesh_requests_including_schema_correction": 56, "images": 0, "judge_calls": 0,
            "note": "Operation cap, not a dollar limit. Authored fixture voice profiles; no profile extraction. No recovery or reroll."}
    if args.plan_only:
        print(json.dumps(plan, indent=2))
        return 0
    if args.output.exists() and any(args.output.iterdir()):
        raise SystemExit("Choose a new, empty output directory; earlier evidence is preserved.")
    settings = load_settings()
    if args.live and not settings.mesh_api_key:
        raise SystemExit("--live requires MESH_API_KEY.")
    settings = replace(settings, data_dir=settings.data_dir / "contract_validation" / str(uuid4()),
                       worker_enabled=False, max_revisions=2)
    report = {"started_at": utcnow(), "mode": "live" if args.live else "fixture", "plan": plan,
              "requested_model": settings.chat_model if args.live else "authored-demo-fixture",
              "limitations": ["Four authored smoke cases are not a representative benchmark.",
                              "Deterministic rules do not establish factual accuracy, writing quality or engagement gains.",
                              "No comparison with the earlier benchmark is controlled; configuration and briefs changed.",
                              "Voice profiles are authored fixtures, not newly learned personal voices."], "cases": []}
    args.output.mkdir(parents=True, exist_ok=True)

    def save():
        temporary = args.output / "results.tmp"
        temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        temporary.replace(args.output / "results.json")

    save()
    store = Store(settings.data_dir)
    try:
        seed_demo(store)
        for case in CASES:
            print(f"Validating {case['id']}", flush=True)
            run = create_run(store, settings, {**case, "mode": "live" if args.live else "demo", "use_learning": False,
                                               "generate_image": False, "feedback_source": "simulated"})
            await run_pipeline(run["id"], store, settings)
            run = store.get("runs", run["id"])
            post = store.get("posts", run["post_id"])
            report["cases"].append({**case, "run": run, "post": post,
                "before_checks": check_contract(post.get("original_draft", ""), run["contract"]),
                "after_checks": check_contract(post.get("content", ""), run["contract"]),
                "completed": run["status"] == "complete"})
            save()
            print(f"  {run['status']}; final rules passed: {report['cases'][-1]['after_checks']['passed']}", flush=True)
    finally:
        store.close()
    report["completed_at"] = utcnow()
    report["summary"] = {"planned": len(CASES), "completed": sum(case["completed"] for case in report["cases"]),
        "passed_before": sum(case["completed"] and case["before_checks"]["passed"] is True for case in report["cases"]),
        "passed_after": sum(case["completed"] and case["after_checks"]["passed"] is True for case in report["cases"]),
        "failed_runs": sum(not case["completed"] for case in report["cases"])}
    save()
    print(json.dumps(report["summary"]))
    return 0 if report["summary"]["completed"] == len(CASES) and report["summary"]["passed_after"] == len(CASES) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    raise SystemExit(asyncio.run(main(parser.parse_args())))

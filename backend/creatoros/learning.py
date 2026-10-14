"""An explicit, inspectable policy; no training or causal uplift is claimed."""
from datetime import datetime, timezone
from uuid import uuid4

HOOKS = ("problem-first", "outcome-first", "question-first")


def build_snapshot(posts: list[dict], feedback: list[dict], brand_id: str,
                   source: str, window: str, version: int) -> dict:
    eligible = {p["id"]: p for p in posts
                if p.get("brand_id") == brand_id
                and p.get("status") in {"published", "published_manually"}
                and p.get("hook") in HOOKS
                and (source == "simulated" or not p.get("is_demo", False))}
    stats = {h: {"hook": h, "posts": 0, "impressions": 0, "comments": 0,
                 "reposts": 0, "rate": None} for h in HOOKS}
    evidence = []
    # Idempotent API upserts are reinforced here for callers importing raw arrays.
    unique = {}
    for f in feedback:
        if (f.get("post_id") in eligible and f.get("source") == source
                and f.get("window") == window and f.get("impressions", 0) > 0):
            unique[f["post_id"]] = f
    for post_id, observation in unique.items():
        stat = stats[eligible[post_id]["hook"]]
        stat["posts"] += 1
        for metric in ("impressions", "comments", "reposts"):
            stat[metric] += observation.get(metric, 0)
        evidence.append(observation["id"])
    for stat in stats.values():
        if stat["impressions"]:
            stat["rate"] = round(1000 * (stat["comments"] + stat["reposts"]) / stat["impressions"], 4)
    observed = [s for s in stats.values() if s["rate"] is not None]
    complete = len(observed) == len(HOOKS)
    best = max(observed, key=lambda s: s["rate"]) if observed else None
    preferred = best["hook"] if complete else None
    if preferred:
        explanation = (
            f"Early signal: {preferred} has the highest observed rate at {best['rate']:.1f} "
            f"comments + reposts per 1,000 impressions across {best['posts']} post(s). "
            "Prefer this opening while exploring every fourth post. This is an association, not causal proof."
        )
    else:
        explanation = (
            f"Collecting evidence: {len(observed)} of 3 hook styles have eligible {window} feedback. "
            "Rotate openings until each has observations. No engagement improvement is claimed."
        )
    return {
        "id": str(uuid4()), "brand_id": brand_id, "source": source, "window": window,
        "version": version, "preferred_hook": preferred, "stats": list(stats.values()),
        "evidence_ids": sorted(evidence), "explanation": explanation,
        "created_at": datetime.now(timezone.utc).isoformat(), "policy": "hook-rate-v1",
        "status": "early_signal" if preferred else "collecting_evidence",
    }


def select_hook(snapshot: dict | None, sequence: int) -> tuple[str, str]:
    """Sequence is zero-based and scoped by brand, provenance, and window."""
    sequence = max(0, sequence)
    if not snapshot or not snapshot.get("preferred_hook"):
        hook = HOOKS[sequence % len(HOOKS)]
        return hook, "Explore hook styles while collecting comparable feedback."
    winner = snapshot["preferred_hook"]
    if (sequence + 1) % 4 == 0:
        alternatives = [h for h in HOOKS if h != winner]
        hook = alternatives[(sequence // 4) % len(alternatives)]
        return hook, "Exploration: every fourth post tests another opening instead of always exploiting the current leader."
    tied = [s["hook"] for s in snapshot["stats"]
            if s["rate"] == max(t["rate"] for t in snapshot["stats"] if t["rate"] is not None)]
    hook = tied[sequence % len(tied)] if len(tied) > 1 else winner
    return hook, snapshot["explanation"]

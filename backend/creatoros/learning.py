"""Inspectable, conservative adaptation; observed associations are not causal uplift."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import random
from uuid import uuid4

HOOKS = ("problem-first", "outcome-first", "question-first")
MIN_POSTS = 3
MIN_IMPRESSIONS = 300
POLICY_VERSION = "hook-rate-v2"


def _interval(observations: list[dict]) -> list[float] | None:
    """Descriptive 90% post-level bootstrap range, not a significance guarantee."""
    if len(observations) < 2:
        return None
    seed = hashlib.sha256(repr([(o["impressions"], o.get("comments", 0), o.get("reposts", 0))
                               for o in observations]).encode()).hexdigest()
    rng = random.Random(seed)
    rates = []
    for _ in range(500):
        sample = rng.choices(observations, k=len(observations))
        rates.append(1000 * sum(o.get("comments", 0) + o.get("reposts", 0) for o in sample)
                     / sum(o["impressions"] for o in sample))
    rates.sort()
    return [round(rates[24], 4), round(rates[474], 4)]


def build_snapshot(posts: list[dict], feedback: list[dict], brand_id: str,
                   source: str, window: str, version: int, platform: str = "linkedin") -> dict:
    eligible = {p["id"]: p for p in posts
                if p.get("brand_id") == brand_id and p.get("platform", "linkedin") == platform
                and p.get("status") in {"published", "published_manually"}
                and p.get("hook") in HOOKS
                and (source == "simulated" or not p.get("is_demo", False))}
    stats = {h: {"hook": h, "posts": 0, "impressions": 0, "comments": 0,
                 "reposts": 0, "rate": None, "interval": None, "sufficient": False} for h in HOOKS}
    unique, excluded = {}, []
    for f in feedback:
        if f.get("post_id") not in eligible or f.get("source") != source or f.get("window") != window:
            continue
        reason = None
        if window not in {"24h", "7d"}:
            reason = "Unknown or cumulative observation window"
        elif f.get("impressions", 0) <= 0:
            reason = "Missing or zero impressions"
        elif source != "simulated" and f.get("timing_status") != "window_matched":
            reason = "Measurement time does not establish a comparable observation window"
        if reason:
            excluded.append({"id": f["id"], "post_id": f["post_id"], "reason": reason})
            continue
        unique[f["post_id"]] = f
    evidence, grouped = [], {h: [] for h in HOOKS}
    for post_id, observation in sorted(unique.items()):
        post = eligible[post_id]
        stat = stats[post["hook"]]
        stat["posts"] += 1
        for metric in ("impressions", "comments", "reposts"):
            stat[metric] += observation.get(metric, 0)
        grouped[post["hook"]].append(observation)
        frozen = deepcopy(observation)
        frozen.update({"feedback_id": observation["id"],
                       "id": observation.get("revision_id", observation["id"]),
                       "post_title": post.get("title", ""), "hook": post["hook"],
                       "content": post.get("content", ""),
                       "opening": post.get("content", "").split("\n", 1)[0],
                       "published_at": post.get("published_at"), "platform": platform})
        evidence.append(frozen)
    for hook, stat in stats.items():
        if stat["impressions"]:
            stat["rate"] = round(1000 * (stat["comments"] + stat["reposts"]) / stat["impressions"], 4)
        stat["interval"] = _interval(grouped[hook])
        stat["sufficient"] = stat["posts"] >= MIN_POSTS and stat["impressions"] >= MIN_IMPRESSIONS
    sufficient = all(s["sufficient"] for s in stats.values())
    observed = [s for s in stats.values() if s["rate"] is not None]
    best = max(observed, key=lambda s: s["rate"]) if observed else None
    separated = bool(sufficient and best and all(
        best["interval"][0] > other["interval"][1]
        for other in stats.values() if other["hook"] != best["hook"]))
    preferred = best["hook"] if separated else None
    status = "early_signal" if preferred else "inconclusive" if sufficient else "collecting_evidence"
    if preferred:
        explanation = (f"Early signal: {preferred} has {best['rate']:.1f} comments + reposts per 1,000 impressions "
                       f"across {best['posts']} posts, with a separated descriptive range. "
                       "Prefer it while exploring every fourth usable draft. This is an association, not causal proof.")
    elif sufficient:
        explanation = "The observed ranges overlap or tie. Keep rotating openings; there is no clear preference yet."
    else:
        explanation = (f"Collecting evidence: require at least {MIN_POSTS} published posts and {MIN_IMPRESSIONS} "
                       "impressions for each opening, with comparable measurement windows. Keep rotating openings.")
    return {"id": str(uuid4()), "brand_id": brand_id, "source": source, "window": window,
            "platform": platform, "version": version, "preferred_hook": preferred,
            "stats": list(stats.values()), "evidence_ids": sorted(e["id"] for e in evidence),
            "evidence": evidence, "evidence_integrity": "frozen", "excluded": excluded,
            "explanation": explanation, "created_at": datetime.now(timezone.utc).isoformat(),
            "policy": POLICY_VERSION, "status": status,
            "thresholds": {"min_posts": MIN_POSTS, "min_impressions": MIN_IMPRESSIONS},
            "uncertainty_note": "90% descriptive post-level bootstrap ranges (500 resamples). Small samples, topic and timing confounding remain; these are not causal confidence intervals."}


def select_hook(snapshot: dict | None, sequence: int) -> tuple[str, str]:
    """Sequence counts usable or reserved drafts, excluding failed attempts."""
    sequence = max(0, sequence)
    if not snapshot or not snapshot.get("preferred_hook"):
        return HOOKS[sequence % len(HOOKS)], "Explore hook styles while collecting sufficient comparable feedback."
    winner = snapshot["preferred_hook"]
    if (sequence + 1) % 4 == 0:
        alternatives = [h for h in HOOKS if h != winner]
        return alternatives[(sequence // 4) % len(alternatives)], "Exploration: every fourth usable draft tests another opening; failed generation attempts do not advance this cadence."
    return winner, snapshot["explanation"]

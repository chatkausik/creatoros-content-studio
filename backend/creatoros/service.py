"""Domain operations shared by HTTP handlers and evaluation scripts."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from .learning import build_snapshot, select_hook
from .store import utcnow


def latest_snapshot(store, brand_id, source, window):
    snapshots = store.list("snapshots", brand_id=brand_id, source=source, window=window)
    return max(snapshots, key=lambda x: x["version"]) if snapshots else None


def create_run(store, settings, payload: dict) -> dict:
    with store.lock:
        brand = store.get("brands", payload["brand_id"])
        if brand is None:
            raise ValueError("Brand not found.")
        if not brand.get("profile"):
            raise ValueError("Learn a brand voice from at least three samples before generating.")
        mode = payload.get("mode", "demo")
        if mode == "live" and not settings.mesh_api_key:
            raise ValueError("Add MESH_API_KEY to your local .env to use live generation.")
        source = payload.get("feedback_source", "simulated" if mode == "demo" else "manual")
        window = payload.get("window", "24h")
        snapshot = latest_snapshot(store, brand["id"], source, window) if payload.get("use_learning", True) else None
        sequence = len([r for r in store.list("runs", brand_id=brand["id"])
                        if r.get("feedback_source") == source and r.get("window") == window])
        hook, reason = select_hook(snapshot, sequence)
        run_id, post_id = str(uuid4()), str(uuid4())
        stamp = utcnow()
        run = {
            "id": run_id, "post_id": post_id, "brand_id": brand["id"], "brief": payload["brief"],
            "status": "queued", "stage": "queued", "error": None, "mode": mode,
            "use_learning": payload.get("use_learning", True), "feedback_source": source,
            "window": window, "generate_image": payload.get("generate_image", False),
            "selected_hook": hook, "strategy_reason": reason,
            "learning_snapshot_id": snapshot["id"] if snapshot else None,
            "learning_version": snapshot["version"] if snapshot else 0,
            "profile": deepcopy(brand["profile"]), "profile_version": brand["profile_version"],
            "evidence_ids": snapshot["evidence_ids"] if snapshot else [],
            "created_at": stamp, "model": settings.chat_model if mode == "live" else "authored-demo-fixture",
        }
        post = {
            "id": post_id, "brand_id": brand["id"], "brief": payload["brief"], "title": "New draft",
            "content": "", "original_draft": "", "status": "generating", "hook": hook,
            "source": "mesh" if mode == "live" else "simulated", "is_demo": mode == "demo",
            "created_at": stamp, "scheduled_at": None, "published_at": None, "image_url": None,
            "run_id": run_id, "profile_version": brand["profile_version"],
            "learning_version": run["learning_version"], "learning_snapshot_id": run["learning_snapshot_id"],
            "versions": [], "reviews": [],
        }
        store.put("posts", post)
        store.put("runs", run)
        store.add_event(post_id, "learning", f"Selected {hook}", reason, run["evidence_ids"], event_id=f"{run_id}:policy")
        return run


def learn(store, brand_id: str, source: str, window: str):
    with store.lock:
        previous = latest_snapshot(store, brand_id, source, window)
        snapshot = build_snapshot(store.list("posts"), store.list("feedback"), brand_id, source, window,
                                  previous["version"] + 1 if previous else 1)
        snapshot["previous_preferred_hook"] = previous.get("preferred_hook") if previous else None
        snapshot["previous_version"] = previous["version"] if previous else 0
        store.put("snapshots", snapshot)
        for fid in snapshot["evidence_ids"]:
            observation = store.get("feedback", fid)
            if observation:
                store.add_event(observation["post_id"], "learner", f"Learning policy v{snapshot['version']}",
                                snapshot["explanation"], snapshot["evidence_ids"],
                                event_id=f"{snapshot['id']}:{observation['post_id']}")
        return snapshot


def hydrate_post(store, post):
    if post is None:
        return None
    obj = deepcopy(post)
    obj["decisions"] = sorted(store.list("events", post_id=post["id"]), key=lambda e: e["created_at"])
    observations = store.list("feedback", post_id=post["id"])
    obj["feedback_observations"] = observations
    obj["feedback"] = max(observations, key=lambda o: o.get("captured_at", "")) if observations else None
    if post.get("learning_snapshot_id"):
        obj["learning_snapshot"] = store.get("snapshots", post["learning_snapshot_id"])
    return obj


def process_due_posts(store, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    changed = 0
    with store.lock:
        for post in store.list("posts", status="scheduled"):
            scheduled_at = datetime.fromisoformat(post["scheduled_at"].replace("Z", "+00:00"))
            if scheduled_at <= now:
                store.patch("posts", post["id"], {"status": "ready_to_publish"})
                store.add_event(post["id"], "scheduler", "Ready to publish", "Scheduled time reached. Publish manually, then confirm here.", event_id=f"due:{post['id']}:{post['scheduled_at']}")
                changed += 1
    return changed

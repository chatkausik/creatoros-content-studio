"""Domain operations shared by HTTP handlers and evaluation scripts."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from .learning import POLICY_VERSION, build_snapshot, select_hook
from .store import utcnow


def latest_snapshot(store, brand_id, source, window, platform="linkedin"):
    snapshots = [s for s in store.list("snapshots", brand_id=brand_id, source=source, window=window)
                 if s.get("platform", "linkedin") == platform]
    return max(snapshots, key=lambda x: x["version"]) if snapshots else None


def create_run(store, settings, payload: dict) -> dict:
    from .pipeline import create_run_manifest
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
        platform = payload.get("platform", "linkedin")
        if platform not in {"linkedin", "newsletter"}:
            raise ValueError("Choose LinkedIn or newsletter.")
        preset = payload.get("model_preset")
        if preset:
            presets = {"budget": "openai/gpt-4o-mini", "submission-tested": "openai/gpt-5.1"}
            if preset not in presets:
                raise ValueError("Unknown model preset.")
            settings = replace(settings, chat_model=presets[preset])
        snapshot = latest_snapshot(store, brand["id"], source, window, platform) if payload.get("use_learning", True) else None
        if snapshot and snapshot.get("policy") != POLICY_VERSION:
            snapshot = learn(store, brand["id"], source, window, platform)
        sequence = len([r for r in store.list("runs", brand_id=brand["id"])
                        if r.get("feedback_source") == source and r.get("window") == window
                        and r.get("platform", "linkedin") == platform
                        and r.get("status") in {"queued", "running", "complete"}])
        hook, reason = select_hook(snapshot, sequence)
        run_id, post_id = str(uuid4()), str(uuid4())
        stamp = utcnow()
        run = {
            "id": run_id, "post_id": post_id, "brand_id": brand["id"], "brief": payload["brief"],
            "status": "queued", "stage": "queued", "error": None, "mode": mode,
            "use_learning": payload.get("use_learning", True), "feedback_source": source,
            "window": window, "generate_image": payload.get("generate_image", False),
            "platform": platform, "model_preset": preset or "configured",
            "manifest": create_run_manifest(settings, platform=platform), "selection_sequence": sequence,
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
            "platform": platform, "image_variants": [], "review_stale": False,
        }
        store.put("posts", post)
        store.put("runs", run)
        store.add_event(post_id, "learning", f"Selected {hook}", reason, run["evidence_ids"], event_id=f"{run_id}:policy")
        return run


def learn(store, brand_id: str, source: str, window: str, platform: str = "linkedin"):
    with store.lock:
        previous = latest_snapshot(store, brand_id, source, window, platform)
        snapshot = build_snapshot(store.list("posts"), store.list("feedback"), brand_id, source, window,
                                  previous["version"] + 1 if previous else 1, platform)
        snapshot["previous_preferred_hook"] = previous.get("preferred_hook") if previous else None
        snapshot["previous_version"] = previous["version"] if previous else 0
        snapshot["previous_snapshot_id"] = previous["id"] if previous else None
        store.put("snapshots", snapshot)
        for observation in snapshot["evidence"]:
            if observation:
                store.add_event(observation["post_id"], "learner", f"Learning policy v{snapshot['version']}",
                                snapshot["explanation"], snapshot["evidence_ids"],
                                event_id=f"{snapshot['id']}:{observation['post_id']}")
        return snapshot


def hydrate_post(store, post):
    if post is None:
        return None
    obj = deepcopy(post)
    obj.setdefault("platform", "linkedin")
    obj["decisions"] = sorted(store.list("events", post_id=post["id"]), key=lambda e: e["created_at"])
    observations = store.list("feedback", post_id=post["id"])
    obj["feedback_observations"] = observations
    obj["feedback_history"] = sorted(store.list("feedback_revisions", post_id=post["id"]),
                                    key=lambda item: item.get("captured_at", ""))
    obj["feedback"] = max(observations, key=lambda o: o.get("captured_at", "")) if observations else None
    if post.get("learning_snapshot_id"):
        obj["learning_snapshot"] = store.get("snapshots", post["learning_snapshot_id"])
        if obj["learning_snapshot"]:
            obj["learning_snapshot"].setdefault("evidence_integrity", "legacy_aggregate_only")
    if obj.get("image_url") and not obj.get("image_variants"):
        obj["image_variants"] = [{"id": "legacy", "url": obj["image_url"],
                                 "source": obj.get("image_source", "unknown"),
                                 "created_at": obj.get("created_at"), "model": obj.get("image_model")}]
        obj["selected_image_variant_id"] = "legacy"
    if obj.get("published_at"):
        from datetime import timedelta
        published = datetime.fromisoformat(obj["published_at"].replace("Z", "+00:00"))
        obj["feedback_reminders"] = [{"window": window, "due_at": (published + delta).isoformat(),
                                      "recorded": any(f["window"] == window and f.get("timing_status") == "window_matched" for f in observations)}
                                     for window, delta in (("24h", timedelta(hours=24)), ("7d", timedelta(days=7)))]
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

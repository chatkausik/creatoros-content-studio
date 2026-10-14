import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.creatoros.config import ROOT, Settings
from backend.creatoros.main import create_app
from backend.creatoros.service import process_due_posts
from backend.creatoros.store import Store


@pytest.fixture
def client(tmp_path):
    settings = Settings(data_dir=tmp_path, worker_enabled=False, mesh_api_key="rsk_test_secret_do_not_return")
    with TestClient(create_app(settings)) as api:
        yield api


def import_post(client, brand_id="brand-ada", **changes):
    body = {"brand_id": brand_id, "title": "A testable workflow", "content": "A published post with concrete evidence and a useful next step.",
            "hook": "problem-first", "published_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(), **changes}
    response = client.post("/api/posts/import", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_feedback_upsert_is_idempotent_and_observation_cohorts_stay_separate(client):
    post = import_post(client)
    other = import_post(client, brand_id="brand-milo")
    endpoint = f"/api/posts/{post['id']}/feedback"
    original = {"impressions": 1000, "comments": 10, "reposts": 5, "source": "manual", "window": "24h",
                "observed_at": (datetime.fromisoformat(post["published_at"]) + timedelta(hours=24)).isoformat()}
    first = client.put(endpoint, json=original)
    second = client.put(endpoint, json={**original, "comments": 20})
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert client.put(endpoint, json={**original, "source": "simulated", "comments": 999}).status_code == 200
    assert client.put(endpoint, json={**original, "window": "7d", "comments": 999}).status_code == 200
    assert client.put(f"/api/posts/{other['id']}/feedback", json={**original, "comments": 999}).status_code == 200
    snapshot = client.post("/api/brands/brand-ada/learn", json={"source": "manual", "window": "24h"}).json()
    assert snapshot["evidence_ids"] == [second.json()["revision_id"]]
    stat = next(s for s in snapshot["stats"] if s["hook"] == "problem-first")
    assert stat["posts"] == 1
    assert stat["impressions"] == 1000
    assert stat["rate"] == 25
    assert len(client.app.state.store.list("feedback", post_id=post["id"])) == 3


def test_run_freezes_brand_profile_and_learning_snapshot(client):
    response = client.post("/api/runs", json={"brand_id": "brand-ada", "brief": "Explain repeatable evaluation for an AI workflow.",
                                              "mode": "demo", "feedback_source": "simulated", "use_learning": True})
    assert response.status_code == 202
    frozen = deepcopy(response.json())
    store = client.app.state.store
    brand = store.get("brands", "brand-ada")
    brand["profile"]["tone"] = "A completely different voice"
    brand["profile_version"] += 1
    store.put("brands", brand)
    for feedback in store.list("feedback"):
        feedback["comments"] = 999 if store.get("posts", feedback["post_id"])["hook"] == "problem-first" else 0
        feedback["reposts"] = 0
        store.put("feedback", feedback)
    new_policy = client.post("/api/brands/brand-ada/learn", json={"source": "simulated", "window": "24h"}).json()
    assert new_policy["preferred_hook"] == "problem-first"
    reloaded = client.get(f"/api/runs/{frozen['id']}").json()["run"]
    for field in ("profile", "profile_version", "selected_hook", "learning_snapshot_id", "learning_version", "evidence_ids"):
        assert reloaded[field] == frozen[field]
    assert frozen["selected_hook"] == "outcome-first"
    assert store.get("snapshots", frozen["learning_snapshot_id"])["preferred_hook"] == "outcome-first"


def test_scheduling_normalizes_timezone_and_recovers_after_restart(tmp_path):
    settings = Settings(data_dir=tmp_path, worker_enabled=False)
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/posts/demo-showcase/approve", json={"acknowledge_unresolved": True}).status_code == 200
        when = datetime.now(timezone(timedelta(hours=-4))) + timedelta(hours=2)
        response = client.post("/api/posts/demo-showcase/schedule", json={"scheduled_at": when.isoformat()})
        assert response.status_code == 200
        assert response.json()["scheduled_at"].endswith("+00:00")
        assert datetime.fromisoformat(response.json()["scheduled_at"]) == when
        assert process_due_posts(client.app.state.store, when - timedelta(seconds=1)) == 0
        # Simulate downtime crossing the scheduled time, without sleeping in a test.
        client.app.state.store.patch("posts", "demo-showcase", {"scheduled_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()})
    with TestClient(create_app(settings)) as restarted:
        post = restarted.get("/api/posts/demo-showcase").json()
        assert post["status"] == "ready_to_publish"
        assert post["published_at"] is None
        due_events = [event for event in post["decisions"] if event["choice"] == "Ready to publish"]
        assert len(due_events) == 1
        assert process_due_posts(restarted.app.state.store) == 0
        assert restarted.post("/api/posts/demo-showcase/publish", json={}).status_code == 200
        published = restarted.get("/api/posts/demo-showcase").json()
        assert published["status"] == "published_manually"


@pytest.mark.parametrize("payload", [
    {}, {"impressions": -1}, {"impressions": 1.5}, {"impressions": True}, {"impressions": "100"},
    {"impressions": 100, "comments": -1}, {"impressions": 100, "window": "3d"},
    {"impressions": 100, "source": "real"},
])
def test_invalid_feedback_rejected(client, payload):
    assert client.put("/api/posts/demo-history-1/feedback", json=payload).status_code == 422


def test_invalid_transitions_and_demo_manual_feedback_rejected(client):
    assert client.put("/api/posts/demo-history-1/feedback", json={"impressions": 100, "source": "manual"}).status_code == 400
    assert client.put("/api/posts/demo-showcase/feedback", json={"impressions": 100, "source": "simulated"}).status_code == 409
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    assert client.post("/api/posts/demo-showcase/schedule", json={"scheduled_at": future}).status_code == 409
    assert client.post("/api/posts/demo-showcase/publish", json={}).status_code == 409
    assert client.post("/api/posts/demo-showcase/approve").status_code == 409
    assert client.post("/api/posts/demo-showcase/approve", json={"acknowledge_unresolved": True}).status_code == 200
    assert client.post("/api/posts/demo-showcase/schedule", json={"scheduled_at": "2099-01-01T12:00:00"}).status_code == 422
    assert client.post("/api/posts/demo-showcase/schedule", json={"scheduled_at": "2000-01-01T12:00:00Z"}).status_code == 422
    assert client.post("/api/posts/demo-showcase/publish", json={"published_at": future}).status_code == 422
    assert client.get("/api/posts/missing").status_code == 404
    assert client.post("/api/runs/demo-run/resume").status_code == 409
    assert client.get("/api/does-not-exist").status_code == 404


def test_zero_impressions_store_safely_but_are_not_used_for_learning(client):
    post = import_post(client)
    response = client.put(f"/api/posts/{post['id']}/feedback", json={"impressions": 0, "comments": 10})
    assert response.status_code == 200
    snapshot = client.post("/api/brands/brand-ada/learn", json={"source": "manual"}).json()
    assert snapshot["evidence_ids"] == []
    assert all(stat["rate"] is None for stat in snapshot["stats"])


def test_finished_post_needs_a_visual_before_scheduling(client):
    client.app.state.store.patch("posts", "demo-showcase", {"image_url": None})
    assert client.post("/api/posts/demo-showcase/approve", json={"acknowledge_unresolved": True}).status_code == 200
    when = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    response = client.post("/api/posts/demo-showcase/schedule", json={"scheduled_at": when})
    assert response.status_code == 409
    assert "visual" in response.json()["detail"]


def test_brand_validation_and_generation_require_a_learned_profile(client):
    texts = ["A sufficiently long writing sample with a clear concrete example.",
             "Another substantial sample discusses how an input affects an output.",
             "A third distinct writing sample asks what a useful result would contain."]
    assert client.post("/api/brands", json={"name": "New", "samples": [{"text": t} for t in texts[:2]]}).status_code == 422
    assert client.post("/api/brands", json={"name": "New", "samples": [{"text": texts[0]}] * 3}).status_code == 422
    response = client.post("/api/brands", json={"name": "New", "samples": [{"text": t} for t in texts]})
    assert response.status_code == 201
    brand = response.json()
    assert client.post("/api/runs", json={"brand_id": brand["id"], "brief": "Explain a concrete engineering task."}).status_code == 400
    profile = client.post(f"/api/brands/{brand['id']}/profile", json={"mode": "demo"})
    assert profile.status_code == 200
    assert profile.json()["profile_source"] == "demo"
    assert profile.json()["profile_version"] == 1


def test_bootstrap_never_exposes_credentials_and_cross_site_writes_fail(client):
    response = client.get("/api/bootstrap")
    assert response.status_code == 200
    assert response.json()["settings"]["mesh_configured"] is True
    assert "rsk_test_secret_do_not_return" not in response.text
    assert "mesh_api_key" not in response.text
    assert not client.get("/assets/%2e%2e/studio.sqlite").content.startswith(b"SQLite format")
    assert client.post("/api/posts/demo-showcase/approve", headers={"Origin": "https://unrelated.example"}).status_code == 403


def test_frontend_built_after_app_creation_and_generated_assets_are_served_separately(tmp_path, monkeypatch):
    import backend.creatoros.main as main
    root = tmp_path / "project"
    monkeypatch.setattr(main, "ROOT", root)
    settings = Settings(data_dir=tmp_path / "data", worker_enabled=False, seed_demo=False)
    app = create_app(settings)
    frontend = root / "frontend" / "dist"
    (frontend / "static").mkdir(parents=True)
    (frontend / "index.html").write_text('<html><script type="module" src="/static/app.js"></script></html>')
    (frontend / "static" / "app.js").write_text('document.title = "CreatorOS";')
    (settings.data_dir / "assets" / "generated.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/studio").text == (frontend / "index.html").read_text()
        script = client.get("/static/app.js")
        assert script.status_code == 200
        assert "javascript" in script.headers["content-type"]
        assert client.get("/assets/generated.svg").headers["content-type"].startswith("image/svg+xml")


def test_current_production_index_references_reachable_assets(client):
    index = ROOT / "frontend" / "dist" / "index.html"
    if not index.is_file():
        pytest.skip("Build frontend before exercising the actual production asset manifest")
    urls = re.findall(r'(?:src|href)="([^"]+\.(?:js|css))"', index.read_text())
    assert urls, "The production page must reference its built JavaScript and CSS"
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200, f"Built asset is unreachable: {url}"
        assert "text/html" not in response.headers["content-type"], f"HTML fallback masked missing asset: {url}"

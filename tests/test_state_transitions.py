"""Protect human work and publishing transitions from resumed or concurrent actions."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.creatoros.config import Settings
from backend.creatoros.main import create_app
from backend.creatoros.service import create_run


@pytest.fixture
def api(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path, worker_enabled=False))) as client:
        yield client


def failed_draft(api, status="failed"):
    store = api.app.state.store
    run = create_run(store, api.app.state.settings, {
        "brand_id": "brand-ada", "brief": "Explain an inspectable evaluation workflow", "mode": "demo",
    })
    example = store.get("posts", "demo-showcase")
    store.patch("posts", run["post_id"], {
        "title": example["title"], "content": example["content"], "status": "needs_review",
        "versions": [{"id": f"{run['id']}:version:0", "kind": "draft", "version": 1, "content": example["content"]}],
        "reviews": [{"id": f"{run['id']}:review:0", "iteration": 0, "approved": False, "requests": []}],
    })
    store.patch("runs", run["id"], {"status": status, "artifacts": {"writer": {"output": {"content": example["content"]}}}})
    return store.get("runs", run["id"])


@pytest.mark.parametrize("status", ["failed", "interrupted"])
def test_unmodified_failed_artifacts_can_still_resume(api, status):
    run = failed_draft(api, status)
    store = api.app.state.store
    original_post = store.get("posts", run["post_id"])
    response = api.post(f"/api/runs/{run['id']}/resume")
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["artifacts"] == run["artifacts"]
    assert store.get("posts", run["post_id"]) == original_post


@pytest.mark.parametrize("change", ["edit", "review", "image", "image_selection", "approval_then_image", "pending_image"])
def test_resume_preserves_human_work_after_a_failed_run(api, change):
    run = failed_draft(api)
    store = api.app.state.store
    endpoint = f"/api/posts/{run['post_id']}"
    if change == "edit":
        post = store.get("posts", run["post_id"])
        assert api.post(endpoint + "/edit", json={
            "content": post["content"] + "\n\nPreserve the original input for every comparison.",
            "reason": "Make the comparison reproducible",
        }).status_code == 200
    elif change == "review":
        response = api.post(endpoint + "/review", json={"mode": "demo"})
        assert response.status_code == 200
        assert response.json()["reviews"][-1]["review_action"] == "manual"
    elif change in {"image", "approval_then_image"}:
        if change == "approval_then_image":
            assert api.post(endpoint + "/approve", json={"acknowledge_unresolved": True}).status_code == 200
        assert api.post(endpoint + "/image", json={"mode": "demo"}).status_code == 200
        if change == "approval_then_image":
            assert store.get("posts", run["post_id"])["status"] == "draft"
    elif change == "image_selection":
        variant = {"id": f"{run['id']}:image:initial", "url": "/assets/original.svg", "source": "demo"}
        store.patch("posts", run["post_id"], {"image_url": variant["url"], "image_variants": [variant]})
        assert api.post(endpoint + "/image/select", json={"variant_id": variant["id"]}).status_code == 200
    else:
        store.patch("posts", run["post_id"], {"pending_image_request": {"id": "manual-request", "mode": "demo"}})
    before_post = store.get("posts", run["post_id"])
    before_run = store.get("runs", run["id"])
    response = api.post(f"/api/runs/{run['id']}/resume")
    assert response.status_code == 409, response.text
    assert "replace that work" in response.json()["detail"]
    assert store.get("posts", run["post_id"]) == before_post
    assert store.get("runs", run["id"]) == before_run


@pytest.mark.parametrize("status", ["approved", "scheduled", "ready_to_publish", "published", "published_manually"])
def test_resume_cannot_reset_a_post_in_the_publishing_workflow(api, status):
    run = failed_draft(api)
    store = api.app.state.store
    store.patch("posts", run["post_id"], {"status": status})
    original = store.get("posts", run["post_id"])
    assert api.post(f"/api/runs/{run['id']}/resume").status_code == 409
    assert store.get("posts", run["post_id"]) == original
    assert store.get("runs", run["id"])["status"] == "failed"


def transition_payload(transition):
    now = datetime.now(timezone.utc)
    return ({"scheduled_at": (now + timedelta(days=1)).isoformat()} if transition == "schedule"
            else {"published_at": (now - timedelta(minutes=1)).isoformat()})


@pytest.mark.parametrize("status", ["queued", "running"])
@pytest.mark.parametrize("transition", ["schedule", "publish"])
def test_publication_transition_rejects_an_active_run(api, status, transition):
    store = api.app.state.store
    assert api.post("/api/posts/demo-showcase/approve", json={"acknowledge_unresolved": True}).status_code == 200
    store.put("runs", {"id": "active-run", "status": status})
    store.patch("posts", "demo-showcase", {"run_id": "active-run"})
    original = store.get("posts", "demo-showcase")
    response = api.post(f"/api/posts/demo-showcase/{transition}", json=transition_payload(transition))
    assert response.status_code == 409
    assert store.get("posts", "demo-showcase") == original


def block_action(monkeypatch, action, started, release):
    import backend.creatoros.pipeline as pipeline

    async def blocked(*args, **kwargs):
        started.set()
        await release.wait()
        if action == "image":
            return {"image_url": "/assets/new-demo.svg", "image_prompt": "A fixture image", "source": "demo", "model": "fixture"}
        return {"approved": False, "requests": [{"issue": "A missing example", "instruction": "Add a concrete input."}], "criteria": [], "source": "demo"}

    monkeypatch.setattr(pipeline, "generate_visual" if action == "image" else "review_post", blocked)


@pytest.mark.parametrize("action", ["image", "review"])
@pytest.mark.parametrize("transition", ["schedule", "publish"])
def test_second_tab_cannot_publish_during_an_awaited_action(tmp_path, monkeypatch, action, transition):
    async def scenario():
        app = create_app(Settings(data_dir=tmp_path, worker_enabled=False))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                endpoint = "/api/posts/demo-showcase"
                assert (await client.post(endpoint + "/approve", json={"acknowledge_unresolved": True})).status_code == 200
                started, release = asyncio.Event(), asyncio.Event()
                block_action(monkeypatch, action, started, release)
                task = asyncio.create_task(client.post(endpoint + f"/{action}", json={"mode": "demo", "regenerate": True}))
                try:
                    await asyncio.wait_for(started.wait(), timeout=5)
                    original = app.state.store.get("posts", "demo-showcase")
                    response = await client.post(endpoint + f"/{transition}", json=transition_payload(transition))
                    assert response.status_code == 409, response.text
                    assert app.state.store.get("posts", "demo-showcase") == original
                finally:
                    release.set()
                    completed = await asyncio.wait_for(task, timeout=5)
                assert completed.status_code == 200, completed.text
                assert completed.json()["status"] == ("draft" if action == "image" else "needs_review")

    asyncio.run(scenario())


@pytest.mark.parametrize("action", ["image", "review"])
@pytest.mark.parametrize("change", ["scheduled", "ready_to_publish", "published_manually", "edited", "run_queued"])
def test_async_completion_preserves_a_newer_post_or_worker_state(tmp_path, monkeypatch, action, change):
    async def scenario():
        app = create_app(Settings(data_dir=tmp_path, worker_enabled=False))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                endpoint = "/api/posts/demo-showcase"
                started, release = asyncio.Event(), asyncio.Event()
                block_action(monkeypatch, action, started, release)
                task = asyncio.create_task(client.post(endpoint + f"/{action}", json={"mode": "demo", "regenerate": True}))
                try:
                    await asyncio.wait_for(started.wait(), timeout=5)
                    store = app.state.store
                    if change == "edited":
                        store.patch("posts", "demo-showcase", {"content": "A newer human revision must remain the current draft.", "review_stale": True})
                    elif change == "run_queued":
                        store.put("runs", {"id": "new-worker-run", "status": "queued"})
                        store.patch("posts", "demo-showcase", {"run_id": "new-worker-run"})
                    else:
                        store.patch("posts", "demo-showcase", {"status": change})
                    original = deepcopy(store.get("posts", "demo-showcase"))
                finally:
                    release.set()
                    completed = await asyncio.wait_for(task, timeout=5)
                assert completed.status_code == 409, completed.text
                assert "current content and publishing decision were preserved" in completed.json()["detail"]
                assert store.get("posts", "demo-showcase") == original

    asyncio.run(scenario())

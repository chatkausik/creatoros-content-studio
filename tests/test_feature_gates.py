import asyncio

from fastapi.testclient import TestClient

from backend.creatoros.config import Settings
from backend.creatoros.main import create_app
from backend.creatoros.pipeline import run_pipeline


def test_newsletter_approval_rechecks_platform_even_when_contract_passes(tmp_path):
    settings = Settings(data_dir=tmp_path, worker_enabled=False)
    with TestClient(create_app(settings)) as client:
        run = client.post("/api/runs", json={"brand_id": "brand-ada", "brief": "A newsletter about reliable AI evaluation workflows",
            "mode": "demo", "platform": "newsletter", "contract": {"max_words": 700}}).json()
        asyncio.run(run_pipeline(run["id"], client.app.state.store, settings))
        post_id = run["post_id"]
        original = client.get(f"/api/runs/{run['id']}").json()["post"]["content"]
        edited = client.post(f"/api/posts/{post_id}/edit", json={"content": "This short edited newsletter omits the required developed sections and supporting details.", "reason": "A short human draft"})
        assert edited.status_code == 200 and edited.json()["contract_checks"]["passed"] is True
        denied = client.post(f"/api/posts/{post_id}/approve", json={"acknowledge_unresolved": True})
        assert denied.status_code == 409 and "platform requirements" in denied.json()["detail"]
        client.post(f"/api/posts/{post_id}/edit", json={"content": original, "reason": "Restore the developed newsletter"})
        assert client.post(f"/api/posts/{post_id}/approve", json={"acknowledge_unresolved": True}).status_code == 200

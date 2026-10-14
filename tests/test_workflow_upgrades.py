"""Cross-layer regressions for editable, versioned learning workflows; no paid calls."""
import asyncio
import hashlib
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.creatoros.config import Settings
from backend.creatoros.main import create_app
from backend.creatoros.mesh import MeshError
from backend.creatoros.pipeline import run_pipeline
from backend.creatoros.service import create_run


@pytest.mark.parametrize("words,adjustment", [(772, "Remove at least 72 words"), (300, "Add at least 100 words")])
def test_newsletter_length_feedback_identifies_actual_count_and_needed_change(words, adjustment):
    from pydantic import ValidationError
    from backend.creatoros.schemas import NewsletterDraft

    with pytest.raises(ValidationError) as failure:
        NewsletterDraft.model_validate({"title": "A useful subject", "content": " ".join(["word"] * words)})
    message = str(failure.value)
    assert f"currently contains {words} words" in message
    assert adjustment in message
    assert "Target 500–550 words" in message


def test_visual_prompt_length_feedback_names_current_size_and_reduction():
    from pydantic import ValidationError
    from backend.creatoros.schemas import VisualBrief

    with pytest.raises(ValidationError) as failure:
        VisualBrief.model_validate({"image_prompt": "x" * 2024, "reason": "A focused depiction of safe retries."})
    message = str(failure.value)
    assert "currently contains 2024 characters" in message
    assert "Remove at least 24 characters" in message
    assert "target 500–1000 characters" in message


def test_strategy_reason_length_feedback_names_current_size_and_reduction():
    from pydantic import ValidationError
    from backend.creatoros.schemas import Strategy

    with pytest.raises(ValidationError) as failure:
        Strategy.model_validate({"angle": "A concrete redaction workflow", "hook": "problem-first", "audience": "Small engineering teams", "outline": ["Name the privacy risk", "Show one redaction", "Explain a limitation"], "reason": "x" * 947})
    message = str(failure.value)
    assert "currently contains 947 characters" in message
    assert "Remove at least 147 characters" in message
    assert "target 200–400 characters" in message


def test_run_cannot_resume_when_its_captured_output_schema_has_changed(api, monkeypatch):
    import backend.creatoros.pipeline as pipeline
    from pydantic import Field

    store, settings = api.app.state.store, api.app.state.settings
    run = create_run(store, settings, {"brand_id": "brand-ada", "brief": "Explain a concrete evaluation workflow", "mode": "demo"})
    original_manifest = deepcopy(run["manifest"])

    class ChangedVisualBrief(pipeline.VisualBrief):
        image_prompt: str = Field(min_length=50, max_length=1500, description="A changed output schema")

    monkeypatch.setattr(pipeline, "VisualBrief", ChangedVisualBrief)
    asyncio.run(run_pipeline(run["id"], store, settings))
    saved = store.get("runs", run["id"])
    assert saved["status"] == "failed"
    assert "output schema hashes" in saved["error"]
    assert saved["manifest"] == original_manifest
    assert not saved.get("artifacts")


def test_older_manifest_does_not_acquire_invented_historical_schema_hashes(api):
    store, settings = api.app.state.store, api.app.state.settings
    run = create_run(store, settings, {"brand_id": "brand-ada", "brief": "Explain a concrete evaluation workflow", "mode": "demo"})
    old_manifest = deepcopy(run["manifest"])
    old_manifest.pop("schema_hashes")
    old_manifest.pop("schema_coverage")
    store.patch("runs", run["id"], {"manifest": old_manifest})
    asyncio.run(run_pipeline(run["id"], store, settings))
    saved = store.get("runs", run["id"])
    assert saved["status"] == "complete"
    assert saved["manifest"]["schema_coverage"] == "uncaptured_legacy_configuration"
    assert "schema_hashes" not in saved["manifest"]
    assert saved["manifest"]["prompt_hashes"] == old_manifest["prompt_hashes"]


@pytest.fixture
def api(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path, worker_enabled=False, mesh_api_key="fake-key-no-inference"))) as client:
        yield client


def published(api, platform="linkedin", **changes):
    payload = {
        "brand_id": "brand-ada", "title": "A concrete evaluation", "content": "A confident answer can hide a missing constraint. Preserve a failing input and compare the response after one controlled change.",
        "hook": "problem-first", "published_at": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
        "platform": platform, **changes,
    }
    response = api.post("/api/posts/import", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def metrics(post, **changes):
    return {"impressions": 1000, "comments": 10, "reposts": 0, "source": "manual", "window": "24h",
            "observed_at": (datetime.fromisoformat(post["published_at"]) + timedelta(hours=24)).isoformat(), **changes}


def learn(api, platform="linkedin"):
    response = api.post("/api/brands/brand-ada/learn", json={"source": "manual", "window": "24h", "platform": platform})
    assert response.status_code == 200, response.text
    return response.json()


def visual(name):
    return {"image_url": f"/assets/{name}.png", "image_prompt": f"An editorial metaphor for {name}",
            "model": "requested-image", "actual_model": "actual-image", "source": "mesh",
            "usage": [{"stage": "image_generation", "model": "requested-image", "actual_model": "actual-image"}],
            "content_sha256": hashlib.sha256(name.encode()).hexdigest(), "request_id": name}


def test_pipeline_image_can_be_regenerated_and_saved_variant_reselected(api, monkeypatch):
    import backend.creatoros.pipeline as pipeline

    store, settings = api.app.state.store, api.app.state.settings
    generation = AsyncMock(side_effect=[visual("initial"), visual("replacement")])
    monkeypatch.setattr(pipeline, "generate_visual", generation)
    run = create_run(store, settings, {"brand_id": "brand-ada", "brief": "Explain a concrete evaluation workflow", "mode": "demo", "generate_image": True})
    asyncio.run(run_pipeline(run["id"], store, settings))
    assert store.get("runs", run["id"])["status"] == "complete"
    endpoint = f"/api/posts/{run['post_id']}"
    first = api.get(endpoint).json()
    original = deepcopy(first["image_variants"][0])
    assert original["url"] == "/assets/initial.png"
    assert original["content_sha256"] == hashlib.sha256(first["content"].encode()).hexdigest()
    assert original["asset_sha256"] == hashlib.sha256(b"initial").hexdigest()
    assert api.post(endpoint + "/image", json={"mode": "live"}).status_code == 200
    assert generation.await_count == 1
    response = api.post(endpoint + "/image", json={"mode": "live", "regenerate": True, "feedback": "Use warmer colors"})
    assert response.status_code == 200, response.text
    second = response.json()
    assert len(second["image_variants"]) == 2
    assert second["image_variants"][0] == original
    assert second["image_url"] == "/assets/replacement.png"
    assert second["image_variants"][1]["feedback"] == "Use warmer colors"
    assert second["image_variants"][1]["asset_sha256"] == hashlib.sha256(b"replacement").hexdigest()
    selected = api.post(endpoint + "/image/select", json={"variant_id": original["id"]})
    assert selected.status_code == 200, selected.text
    assert selected.json()["image_url"] == original["url"]
    assert not selected.json()["image_stale"]
    assert generation.await_count == 2


def test_failed_image_attempt_preserves_selection_and_reuses_pending_request(api, monkeypatch):
    import backend.creatoros.pipeline as pipeline

    endpoint = "/api/posts/demo-showcase"
    before = api.get(endpoint).json()
    generation = AsyncMock(side_effect=[MeshError("Temporary image download failure", {"image_retry_action": "retry_download"}), visual("retry")])
    monkeypatch.setattr(pipeline, "generate_visual", generation)
    payload = {"mode": "live", "regenerate": True, "feedback": "More negative space"}
    assert api.post(endpoint + "/image", json=payload).status_code == 502
    failed = api.get(endpoint).json()
    assert failed["image_url"] == before["image_url"]
    pending_id = failed["pending_image_request"]["id"]
    recovered = api.post(endpoint + "/image", json=payload)
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["pending_image_request"] is None
    assert generation.await_args_list[0].kwargs["regeneration_id"] == pending_id
    assert generation.await_args_list[1].kwargs["regeneration_id"] == pending_id
    assert len(recovered.json()["image_variants"]) == len(before["image_variants"]) + 1


def test_pending_image_download_retry_keeps_its_original_model_configuration(api, monkeypatch):
    import backend.creatoros.pipeline as pipeline

    settings = api.app.state.settings
    settings.image_model = "original-image-model"
    requested = []

    async def generate(_post, config, **kwargs):
        requested.append((config.image_model, kwargs["regeneration_id"]))
        if len(requested) == 1:
            raise MeshError("Temporary image download failure", {"image_retry_action": "retry_download"})
        return visual("recovered-frozen-request")

    monkeypatch.setattr(pipeline, "generate_visual", generate)
    payload = {"mode": "live", "regenerate": True, "feedback": "Use a calmer palette"}
    endpoint = "/api/posts/demo-showcase/image"
    assert api.post(endpoint, json=payload).status_code == 502
    settings.image_model = "new-image-model"
    response = api.post(endpoint, json=payload)
    assert response.status_code == 200, response.text
    assert requested[0] == requested[1]
    assert requested[1][0] == "original-image-model"
    assert response.json()["image_variants"][-1]["manifest"]["image_model"] == "original-image-model"


def test_manual_edit_requires_acknowledgment_and_new_review_preserves_history(api, monkeypatch):
    import backend.creatoros.pipeline as pipeline

    endpoint = "/api/posts/demo-showcase"
    api.app.state.store.patch("posts", "demo-showcase", {"image_url": None, "image_variants": []})
    original = api.get(endpoint).json()
    edited = original["content"] + "\n\nKeep the exact input beside both responses so another reviewer can inspect the comparison."
    response = api.post(endpoint + "/edit", json={"content": edited, "title": "A better comparison", "reason": "Make the evidence inspectable"})
    assert response.status_code == 200
    first = response.json()
    assert first["review_stale"]
    assert first["reviews"] == original["reviews"]
    assert first["versions"][-1]["kind"] == "human_edit"
    assert first["versions"][-1]["title"] == "A better comparison"
    assert first["versions"][-1]["source"] == "human"
    assert api.post(endpoint + "/approve").status_code == 409
    acknowledged = api.post(endpoint + "/approve", json={"acknowledge_unresolved": True})
    assert acknowledged.status_code == 200
    assert acknowledged.json()["review_stale"]
    edited_again = edited + " Record the reviewer's reason as well."
    assert api.post(endpoint + "/edit", json={"content": edited_again, "reason": "Preserve the reviewer decision"}).status_code == 200
    review = {"iteration": 3, "criteria": [{"name": name, "score": 4, "reason": "The current text satisfies this criterion."} for name in ("brief_fulfillment", "specificity", "clarity", "brand_fit", "factual_care")], "requests": [], "approved": True,
              "model": "test-editor", "actual_model": "actual-test-editor", "source": "mesh", "usage": []}
    reviewer = AsyncMock(return_value=review)
    monkeypatch.setattr(pipeline, "review_post", reviewer)
    result = api.post(endpoint + "/review", json={"mode": "live"})
    assert result.status_code == 200, result.text
    post = result.json()
    assert reviewer.await_args.args[0]["content"] == edited_again
    assert post["reviews"][:-1] == original["reviews"]
    assert not post["review_stale"]
    assert post["reviews"][-1]["content_sha256"] == hashlib.sha256(edited_again.encode()).hexdigest()
    assert api.post(endpoint + "/approve").status_code == 200


@pytest.mark.parametrize("operation", ["regenerate", "select"])
@pytest.mark.parametrize("latest_review", [
    {"approved": False, "requests": []},
    {"approved": True, "requests": [{"issue": "The example is incomplete", "instruction": "Specify the input and expected response in the worked example."}]},
    {"approved": True, "requests": [], "requires_human_review": True},
])
def test_image_changes_cannot_hide_unresolved_latest_editor_review(api, monkeypatch, operation, latest_review):
    import backend.creatoros.pipeline as pipeline

    endpoint = "/api/posts/demo-showcase"
    original = api.get(endpoint).json()
    reviews = [*original["reviews"], {"iteration": 9, **latest_review}]
    api.app.state.store.patch("posts", "demo-showcase", {"status": "needs_review", "reviews": reviews, "review_stale": False, "image_stale": False})
    # A human can acknowledge the concern, but a changed visual requires a new approval.
    assert api.post(endpoint + "/approve", json={"acknowledge_unresolved": True}).status_code == 200
    monkeypatch.setattr(pipeline, "generate_visual", AsyncMock(return_value=visual("changed-visual")))
    if operation == "regenerate":
        changed = api.post(endpoint + "/image", json={"mode": "live", "regenerate": True})
    else:
        changed = api.post(endpoint + "/image/select", json={"variant_id": original["selected_image_variant_id"]})
    assert changed.status_code == 200, changed.text
    assert changed.json()["status"] == "draft"
    assert not changed.json()["review_stale"]
    assert changed.json()["reviews"][-1] == reviews[-1]
    assert api.post(endpoint + "/approve").status_code == 409
    acknowledged = api.post(endpoint + "/approve", json={"acknowledge_unresolved": True})
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "approved"
    assert acknowledged.json()["reviews"][-1] == reviews[-1]


def test_feedback_exact_retry_is_idempotent_and_correction_preserves_snapshot(api):
    post = published(api)
    endpoint = f"/api/posts/{post['id']}/feedback"
    payload = metrics(post)
    first = api.put(endpoint, json=payload).json()
    snapshot = learn(api)
    frozen = deepcopy(snapshot)
    repeated = api.put(endpoint, json=payload).json()
    assert repeated == first
    assert len(api.app.state.store.list("feedback_revisions", post_id=post["id"])) == 1
    corrected = api.put(endpoint, json={**payload, "comments": 90}).json()
    assert corrected["id"] == first["id"]
    assert corrected["revision_id"] != first["revision_id"]
    assert corrected["revision"] == 2
    assert api.app.state.store.get("feedback_revisions", first["revision_id"])["comments"] == 10
    assert api.app.state.store.get("snapshots", snapshot["id"]) == frozen
    assert snapshot["evidence_ids"] == [first["revision_id"]]
    assert snapshot["evidence"][0]["comments"] == 10
    current = learn(api)
    assert current["evidence_ids"] == [corrected["revision_id"]]
    assert current["stats"][0]["rate"] == 90
    assert len(api.get(f"/api/posts/{post['id']}").json()["feedback_history"]) == 2


@pytest.mark.parametrize("window,observed", [("unknown", "expected"), ("cumulative", "expected"), ("24h", None), ("24h", "late")])
def test_unverified_or_incomparable_metrics_are_saved_but_excluded(api, window, observed):
    post = published(api)
    observation_time = (datetime.fromisoformat(post["published_at"]) + timedelta(hours=24 if observed == "expected" else 48)).isoformat() if observed else None
    response = api.put(f"/api/posts/{post['id']}/feedback", json=metrics(post, window=window, observed_at=observation_time))
    assert response.status_code == 200, response.text
    assert response.json()["timing_status"] in {"unverified", "out_of_window"}
    snapshot = learn(api)
    assert snapshot["evidence"] == []
    assert snapshot["stats"][0]["posts"] == 0
    assert len(api.get(f"/api/posts/{post['id']}").json()["feedback_history"]) == 1


def test_explicit_first_day_interval_can_be_captured_later(api):
    post = published(api)
    start = datetime.fromisoformat(post["published_at"])
    payload = metrics(post, window_start=start.isoformat(), window_end=(start + timedelta(hours=24)).isoformat(), observed_at=(start + timedelta(days=3)).isoformat())
    response = api.put(f"/api/posts/{post['id']}/feedback", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["timing_status"] == "window_matched"
    assert response.json()["window_basis"] == "declared_interval"
    assert learn(api)["evidence_ids"] == [response.json()["revision_id"]]


def test_partial_interval_and_incompatible_interval_are_not_accepted_as_comparable(api):
    post = published(api)
    start = datetime.fromisoformat(post["published_at"])
    endpoint = f"/api/posts/{post['id']}/feedback"
    partial = api.put(endpoint, json=metrics(post, window_start=start.isoformat()))
    assert partial.status_code == 422
    wrong = api.put(endpoint, json=metrics(post, window_start=(start + timedelta(hours=1)).isoformat(), window_end=(start + timedelta(hours=25)).isoformat(), observed_at=(start + timedelta(days=3)).isoformat()))
    assert wrong.status_code == 200
    assert wrong.json()["timing_status"] == "out_of_window"
    assert learn(api)["evidence"] == []


def test_invalid_short_manual_edit_review_returns_actionable_validation_not_gateway_error(api, monkeypatch):
    from backend.creatoros.mesh import MeshClient

    call = AsyncMock()
    monkeypatch.setattr(MeshClient, "_post", call)
    endpoint = "/api/posts/demo-showcase"
    assert api.post(endpoint + "/edit", json={"content": "A short unfinished draft needs more detail.", "reason": "Save an unfinished revision"}).status_code == 200
    response = api.post(endpoint + "/review", json={"mode": "live"})
    assert response.status_code == 422
    assert "review requirements" in response.json()["detail"]
    call.assert_not_awaited()


def test_new_image_action_on_old_completed_run_uses_new_manifest_without_rewriting_run(api, monkeypatch):
    import backend.creatoros.pipeline as pipeline

    store, settings = api.app.state.store, api.app.state.settings
    run = create_run(store, settings, {"brand_id": "brand-ada", "brief": "Explain a concrete evaluation workflow", "mode": "demo"})
    asyncio.run(run_pipeline(run["id"], store, settings))
    original = store.get("runs", run["id"])
    old_manifest = deepcopy(original["manifest"])
    old_manifest["pipeline_version"] = old_manifest["prompt_version"] = "old-release"
    old_manifest["chat_model"] = "old-model"
    store.patch("runs", run["id"], {"manifest": old_manifest})
    generation = AsyncMock(return_value=visual("new-action"))
    monkeypatch.setattr(pipeline, "generate_visual", generation)
    response = api.post(f"/api/posts/{run['post_id']}/image", json={"mode": "live", "regenerate": True})
    assert response.status_code == 200, response.text
    assert generation.await_args.args[1].chat_model == settings.chat_model
    assert response.json()["image_variants"][-1]["manifest"]["prompt_version"] == pipeline.prompts.PROMPT_VERSION
    assert store.get("runs", run["id"])["manifest"] == old_manifest


def test_learning_and_exploration_sequences_do_not_mix_platforms(api):
    linkedin, newsletter = published(api), published(api, "newsletter")
    li = api.put(f"/api/posts/{linkedin['id']}/feedback", json=metrics(linkedin)).json()
    news = api.put(f"/api/posts/{newsletter['id']}/feedback", json=metrics(newsletter, comments=999)).json()
    li_snapshot, news_snapshot = learn(api), learn(api, "newsletter")
    assert li_snapshot["evidence_ids"] == [li["revision_id"]]
    assert news_snapshot["evidence_ids"] == [news["revision_id"]]
    assert li_snapshot["stats"][0]["rate"] == 10
    assert news_snapshot["stats"][0]["rate"] == 999
    store, settings = api.app.state.store, api.app.state.settings
    payload = {"brand_id": "brand-ada", "brief": "Explain a concrete evaluation workflow", "mode": "demo", "feedback_source": "manual"}
    first = create_run(store, settings, {**payload, "platform": "linkedin"})
    second = create_run(store, settings, {**payload, "platform": "newsletter"})
    assert first["selection_sequence"] == second["selection_sequence"] == 0
    assert first["learning_snapshot_id"] == li_snapshot["id"]
    assert second["learning_snapshot_id"] == news_snapshot["id"]
    assert second["manifest"]["platform"] == "newsletter"


def test_failed_and_interrupted_runs_do_not_advance_exploration(api):
    store, settings = api.app.state.store, api.app.state.settings
    payload = {"brand_id": "brand-ada", "brief": "Explain a concrete evaluation workflow", "mode": "demo", "feedback_source": "manual", "use_learning": False}
    failed = create_run(store, settings, payload)
    store.patch("runs", failed["id"], {"status": "failed"})
    interrupted = create_run(store, settings, payload)
    store.patch("runs", interrupted["id"], {"status": "interrupted"})
    next_run = create_run(store, settings, payload)
    assert failed["selection_sequence"] == interrupted["selection_sequence"] == next_run["selection_sequence"] == 0
    assert failed["selected_hook"] == interrupted["selected_hook"] == next_run["selected_hook"] == "problem-first"
    store.patch("runs", next_run["id"], {"status": "complete"})
    following = create_run(store, settings, payload)
    assert following["selection_sequence"] == 1
    assert following["selected_hook"] == "outcome-first"


@pytest.mark.parametrize("action,payload", [("approve", {"acknowledge_unresolved": True}), ("image", {"mode": "demo", "regenerate": True})])
def test_resumed_generation_cannot_be_approved_or_receive_competing_image(api, monkeypatch, action, payload):
    import backend.creatoros.pipeline as pipeline

    store, settings = api.app.state.store, api.app.state.settings
    run = create_run(store, settings, {"brand_id": "brand-ada", "brief": "Explain a concrete evaluation workflow", "mode": "demo"})
    store.patch("runs", run["id"], {"status": "failed"})
    store.patch("posts", run["post_id"], {"status": "needs_review", "content": "A saved draft from an interrupted generation still needs its editor review. Preserve the partial work and finish that review before deciding whether it is ready."})
    assert api.post(f"/api/runs/{run['id']}/resume").status_code == 202
    generation = AsyncMock(return_value=visual("unexpected"))
    monkeypatch.setattr(pipeline, "generate_visual", generation)
    response = api.post(f"/api/posts/{run['post_id']}/{action}", json=payload)
    assert response.status_code == 409
    generation.assert_not_awaited()

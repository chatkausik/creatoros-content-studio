"""Behavior checks: real graph, durable artifacts, gateway and asset boundaries."""
import asyncio
import base64
import json
from unittest.mock import AsyncMock

import pytest

from backend.creatoros.config import Settings
from backend.creatoros.fixtures import ADA_SAMPLES, seed_demo
from backend.creatoros.mesh import MeshClient, MeshError, normalize_image
from backend.creatoros.pipeline import _substantive, extract_profile, generate_visual, run_pipeline
from backend.creatoros.schemas import Draft
from backend.creatoros.service import create_run
from backend.creatoros.store import Store


def setup_studio(tmp_path):
    settings = Settings(data_dir=tmp_path, demo_mode=True)
    store = Store(tmp_path)
    seed_demo(store)
    return store, settings


def make_run(store, settings, brand="brand-ada"):
    return create_run(store, settings, {"brand_id": brand, "brief": "A LinkedIn post about AI safety", "mode": "demo", "generate_image": False, "use_learning": True, "feedback_source": "simulated"})


def test_graph_makes_revision_and_preserves_artifacts(tmp_path):
    store, settings = setup_studio(tmp_path)
    run = make_run(store, settings)
    asyncio.run(run_pipeline(run["id"], store, settings))
    saved = store.get("runs", run["id"])
    post = store.get("posts", run["post_id"])
    assert saved["status"] == "complete", saved.get("error")
    assert post["status"] == "draft"
    assert post["hook"] == run["selected_hook"]
    assert _substantive(post["original_draft"], post["content"])
    assert len(post["versions"]) == 2
    assert len(post["reviews"]) == 2
    assert post["reviews"][0]["requests"]
    assert post["reviews"][1]["approved"]
    assert post["image_url"] is None
    events_before = store.list("events", post_id=post["id"])
    asyncio.run(run_pipeline(run["id"], store, settings))
    assert store.get("posts", post["id"])["versions"] == post["versions"]
    assert store.list("events", post_id=post["id"]) == events_before
    assert (tmp_path / "checkpoints.sqlite").is_file()


def test_graph_resumes_failure_without_rewriting_completed_draft(tmp_path, monkeypatch):
    from backend.creatoros import pipeline

    store, settings = setup_studio(tmp_path)
    run = make_run(store, settings)
    real_review = pipeline._demo_review
    monkeypatch.setattr(pipeline, "_demo_review", lambda _: (_ for _ in ()).throw(RuntimeError("private upstream detail")))
    asyncio.run(run_pipeline(run["id"], store, settings))
    failed = store.get("runs", run["id"])
    first_version = store.get("posts", run["post_id"])["versions"][0]
    assert failed["status"] == "failed"
    assert "private upstream" not in failed["error"]
    monkeypatch.setattr(pipeline, "_demo_review", real_review)
    asyncio.run(run_pipeline(run["id"], Store(tmp_path), settings))
    post = store.get("posts", run["post_id"])
    assert store.get("runs", run["id"])["status"] == "complete"
    assert len(post["versions"]) == 2
    assert post["versions"][0] == first_version
    assert len([e for e in store.list("events", post_id=post["id"]) if e["id"] == f"{run['id']}:writer"]) == 1


def test_distinct_voice_profiles_change_demo_writing(tmp_path):
    store, settings = setup_studio(tmp_path)
    first, second = make_run(store, settings, "brand-ada"), make_run(store, settings, "brand-milo")
    asyncio.run(run_pipeline(first["id"], store, settings))
    asyncio.run(run_pipeline(second["id"], store, settings))
    ada = store.get("posts", first["post_id"])["content"]
    milo = store.get("posts", second["post_id"])["content"]
    assert "1. Record" in ada
    assert "Imagine a rehearsal" in milo


def test_demo_profile_requires_multiple_distinct_samples(tmp_path):
    settings = Settings(data_dir=tmp_path)
    with pytest.raises(ValueError, match="three distinct"):
        asyncio.run(extract_profile([{"text": ADA_SAMPLES[0]}] * 3, settings, "demo"))
    result = asyncio.run(extract_profile([{"text": sample} for sample in ADA_SAMPLES], settings, "demo"))
    assert len(result["evidence"]) >= 3
    assert "Illustrative demo" in result["summary"]


def test_gateway_bounds_validation_retry_and_caches_success(tmp_path):
    client = MeshClient(Settings(data_dir=tmp_path, mesh_api_key="fake-key"))
    invalid = {"choices": [{"message": {"content": '{"title":"x", "content":"short"}'}}]}
    valid = {"choices": [{"message": {"content": json.dumps({"title": "A useful title", "content": "A concrete example. " * 12})}}], "usage": {"total_tokens": 42}}
    client._post = AsyncMock(side_effect=[invalid, valid])
    result = asyncio.run(client.complete_json("System", "User", Draft))
    assert result.title == "A useful title"
    assert client._post.await_count == 2
    assert asyncio.run(client.complete_json("System", "User", Draft)) == result
    assert client._post.await_count == 2
    assert client.usage[-1]["cache_hit"]


def test_gateway_stops_after_two_invalid_outputs(tmp_path):
    client = MeshClient(Settings(data_dir=tmp_path, mesh_api_key="fake-key"))
    client._post = AsyncMock(return_value={"choices": [{"message": {"content": "not json"}}]})
    with pytest.raises(MeshError, match="twice") as failure:
        asyncio.run(client.complete_json("System", "User", Draft))
    assert client._post.await_count == 2
    assert failure.value.diagnostics["schema"] == "Draft"
    assert failure.value.diagnostics["attempt"] == 2
    assert "input" not in failure.value.diagnostics["errors"][0]
    assert client._post.await_args_list[1].kwargs["cache"] is False
    corrected_messages = client._post.await_args_list[1].args[1]["messages"]
    assert corrected_messages[-2] == {"role": "assistant", "content": "not json"}
    assert len(list((tmp_path / "mesh_diagnostics").glob("*.json"))) == 2


def test_images_accept_mesh_data_uri_and_reject_private_urls():
    data = b"\x89PNG\r\n\x1a\n" + b"example"
    encoded = base64.b64encode(data).decode()
    assert asyncio.run(normalize_image({"url": "data:image/png;base64," + encoded})) == data
    assert asyncio.run(normalize_image({"b64_json": encoded})) == data
    with pytest.raises(MeshError, match="public"):
        asyncio.run(normalize_image({"url": "https://127.0.0.1/private"}))
    with pytest.raises(MeshError, match="public HTTPS"):
        asyncio.run(normalize_image({"url": "http://example.com/image.png"}))
    with pytest.raises(MeshError, match="unsupported"):
        asyncio.run(normalize_image({"url": "data:text/html;base64," + encoded}))


def test_demo_visual_is_honestly_labeled(tmp_path):
    settings = Settings(data_dir=tmp_path)
    result = asyncio.run(generate_visual({"title": "AI safety", "content": "Sample"}, settings, "demo"))
    assert result["source"] == "demo"
    assert "not AI-generated" in (tmp_path / result["image_url"].lstrip("/")).read_text()


def test_revision_rejects_cosmetic_changes():
    assert not _substantive("This is the same draft!", "This is the same draft.")


def test_editor_loop_stops_after_two_revisions_with_unresolved_issues(tmp_path, monkeypatch):
    from backend.creatoros.pipeline import _demo_review

    store, settings = setup_studio(tmp_path)
    settings.mesh_api_key = "fake-key"
    run = create_run(store, settings, {"brand_id": "brand-ada", "brief": "AI safety", "mode": "live", "generate_image": False})
    call_names = []
    revisions = 0

    async def answer(_client, system, user, schema, temperature=0.2, cache=True):
        nonlocal revisions
        call_names.append(schema.__name__)
        if schema.__name__ == "SelectedStrategy":
            return schema.model_validate({"angle": "Test a concrete AI safety failure", "hook": run["selected_hook"], "audience": "AI engineers", "outline": ["Name the failure", "Describe the test", "Ask for an example"], "reason": "Follow the brief with one practical test."})
        if schema.__name__ == "PolicyDraft":
            return schema.model_validate({"title": "Test AI safety", "content": "Test a difficult AI safety case before expanding the workflow. Save the input, write the expected response, and inspect the actual result. " * 2})
        if "Review" in schema.__name__:
            return schema.model_validate(_demo_review(0))
        if schema.__name__ == "SubstantiveRevision":
            revisions += 1
            content = (
                "A concrete safety check begins with an ambiguous request. Ask the system to clarify missing context, compare this response with an immediate answer, and record what each version invented. Keep the input fixed while changing one instruction."
                if revisions == 1 else
                "Build a small safety review around three difficult inputs. First, document what the system is allowed to do. Then compare its response with that boundary. Finally, preserve a failing case and check it after your next change. An ambiguous request is a useful hypothetical starting point."
            )
            return schema.model_validate({"title": "A concrete safety check", "content": content, "addressed_requests": ["Replaced vague advice with a practical sequence and hypothetical test."]})
        raise AssertionError(schema.__name__)

    monkeypatch.setattr(MeshClient, "complete_json", answer)
    asyncio.run(run_pipeline(run["id"], store, settings))
    post = store.get("posts", run["post_id"])
    assert store.get("runs", run["id"])["status"] == "complete"
    assert post["status"] == "needs_review"
    assert len(post["versions"]) == 3
    assert len(post["reviews"]) == 3
    assert revisions == 2
    assert call_names.count("SubstantiveRevision") == 2


def test_live_profile_rejects_ungrounded_quotes_with_one_correction(tmp_path, monkeypatch):
    from backend.creatoros.pipeline import _demo_profile

    samples = [{"text": text} for text in ADA_SAMPLES]
    valid = _demo_profile(samples)
    invalid = {**valid, "evidence": [{"trait": "Invented evidence", "quote": "This quote does not appear in any supplied sample."}] * 3}
    responses = [
        {"choices": [{"message": {"content": json.dumps(value)}}]}
        for value in (invalid, valid)
    ]
    mocked = AsyncMock(side_effect=responses)
    monkeypatch.setattr(MeshClient, "_post", mocked)
    profile = asyncio.run(extract_profile(samples, Settings(data_dir=tmp_path, mesh_api_key="fake-key"), "live"))
    assert profile["evidence"] == valid["evidence"]
    assert mocked.await_count == 2


def test_uncached_inference_disables_gateway_cache_and_records_actual_model(tmp_path, monkeypatch):
    import httpx
    from contextlib import asynccontextmanager

    response_body = {"model": "openai/actual-model", "usage": {"total_tokens": 11}, "choices": [{"message": {"content": json.dumps({"title": "A useful title", "content": "A concrete example. " * 12})}}]}
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=response_body)

    original_client = httpx.AsyncClient

    @asynccontextmanager
    async def fake_client(**kwargs):
        async with original_client(transport=httpx.MockTransport(handle)) as client:
            yield client

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    client = MeshClient(Settings(data_dir=tmp_path, mesh_api_key="fake-key"))
    for _ in range(2):
        asyncio.run(client.complete_json("System", "User", Draft, cache=False))
    assert len(requests) == 2
    assert all(request.headers["X-Mesh-Cache"] == "no-store" for request in requests)
    assert all(str(request.url) == "https://api.meshapi.ai/v1/chat/completions" for request in requests)
    assert client.usage[-1]["actual_model"] == "openai/actual-model"
    assert not list((tmp_path / "mesh_cache").glob("*.json"))


def test_post_schema_rejects_content_over_linkedin_limit():
    from pydantic import ValidationError
    from backend.creatoros.schemas import Revision

    with pytest.raises(ValidationError):
        Draft.model_validate({"title": "Too long", "content": "x" * 3001})
    with pytest.raises(ValidationError):
        Revision.model_validate({"title": "Too long", "content": "x" * 3001, "addressed_requests": ["Expanded example"]})

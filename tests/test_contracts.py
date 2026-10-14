"""Brief constraints remain observable and binding despite optimistic editor scores."""
import asyncio
from copy import deepcopy
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from backend.creatoros.config import Settings
from backend.creatoros.contracts import Contract, check_contract, suggest_contract, validate_contract
from backend.creatoros.fixtures import seed_demo
from backend.creatoros.mesh import MeshClient
from backend.creatoros.main import create_app
from backend.creatoros.pipeline import _demo_review, review_post, run_pipeline
from backend.creatoros.service import create_run
from backend.creatoros.store import Store


@pytest.mark.parametrize("contract", [
    {"min_words": True}, {"max_words": "150"}, {"max_words": 150.0},
    {"max_words": -1}, {"max_words": 10001}, {"min_bullets": 101},
    {"plain_text": "true"}, {"extra_rule": 1},
    {"min_words": 151, "max_words": 150}, {"min_bullets": 4, "max_bullets": 3},
    {"required_sections": ["Summary", " summary: "]},
    {"required_sections": [" "]}, {"required_sections": ["Two\nlines"]},
    {"required_sections": ["# Heading"]},
    {"max_words": 1, "required_sections": ["Two words"]},
])
def test_contract_rejects_invalid_or_ambiguous_values(contract):
    with pytest.raises(ValueError):
        Contract.model_validate(contract)


@pytest.mark.parametrize("contract,platform", [
    ({"max_characters": 3001}, "linkedin"), ({"max_characters": 99}, "linkedin"),
    ({"max_words": 0}, "linkedin"), ({"min_words": 1501}, "linkedin"),
    ({"min_words": 100, "max_characters": 150}, "linkedin"),
    ({"max_words": 399}, "newsletter"), ({"min_words": 701}, "newsletter"),
    ({"max_words": 701}, "newsletter"), ({"max_characters": 700}, "newsletter"),
])
def test_contract_checks_platform_compatibility(contract, platform):
    with pytest.raises(ValueError):
        validate_contract(contract, platform)


def test_contract_counts_body_and_normalizes_heading_whitespace():
    content = "A concrete opening.\r\n\r\n  Try   it:  \r\n\r\n- One step\n2. Another step\n\nBare https://example.test #AI"
    contract = validate_contract({"min_words": 14, "max_words": 20, "max_characters": 200,
                                  "min_bullets": 2, "max_bullets": 2, "max_hashtags": 1,
                                  "required_sections": [" Try it: "], "plain_text": True})
    assert contract["required_sections"] == ["Try it"]
    result = check_contract(content, contract)
    assert result["passed"] is True
    assert result["counts"] == {"words": 14, "characters": len(content), "bullets": 2, "hashtags": 1}
    assert result["content_sha256"] == hashlib.sha256(content.encode()).hexdigest()
    assert result["violations"] == []
    assert check_contract("Please Try it somewhere inside this paragraph.", {"required_sections": ["Try it"]})["passed"] is False


@pytest.mark.parametrize("formatted", ["**bold**", "# Heading", "`code`", "[label](https://example.test)", "<b>bold</b>", "*italic*", "> quoted"])
def test_contract_plain_text_rejects_common_markup(formatted):
    assert check_contract(formatted, {"plain_text": True})["passed"] is False


def test_empty_contract_is_unassessed_and_zero_bullet_limit_is_enforced():
    assert check_contract("Any draft", None)["passed"] is None
    assert check_contract("Any draft", {})["checks"] == []
    result = check_contract("- A bullet\n\n#tag", {"max_bullets": 0, "max_hashtags": 0})
    assert result["passed"] is False
    assert len(result["violations"]) == 2


def test_suggestions_are_conservative_explicit_and_do_not_call_a_model():
    result = suggest_contract("Write 100–150 words, at least 2 bullets, no hashtags, plain text.", "linkedin")
    assert result["contract"] == {"min_words": 100, "max_words": 150, "min_bullets": 2, "max_hashtags": 0, "required_sections": [], "plain_text": True}
    assert result["warnings"]
    assert suggest_contract("Under 150 words, exactly 3 bullets.")["contract"]["max_words"] == 149
    assert suggest_contract("No fewer than 150 words.")["contract"]["min_words"] == 150
    assert "max_words" not in suggest_contract("Do not use at most 150 words.")["contract"]
    ambiguous = suggest_contract("Write around 150 words in three sections.")
    assert "max_words" not in ambiguous["contract"]
    assert any("ambiguous" in warning for warning in ambiguous["warnings"])


@pytest.mark.parametrize("brief,platform", [
    ("At least 200 words and at most 150 words.", "linkedin"),
    ("At most 150 words, but at most 100 words.", "linkedin"),
    ("At most 999999 words.", "linkedin"),
    ("100–150 words.", "newsletter"),
])
def test_contradictory_or_oversized_suggestions_are_not_silently_applied(brief, platform):
    result = suggest_contract(brief, platform)
    assert "min_words" not in result["contract"]
    assert "max_words" not in result["contract"]
    assert any("conflict" in warning for warning in result["warnings"])


def test_huge_numeric_suggestion_is_rejected_without_integer_conversion_failure():
    result = suggest_contract("At most " + "9" * 5000 + " words.")
    assert "max_words" not in result["contract"]
    assert any("limits" in warning for warning in result["warnings"])


def _content(prefix, words):
    return "Fragile workflows hide mistakes. " + " ".join(f"{prefix}{index}" for index in range(words - 4))


def _run(tmp_path, monkeypatch, final_words=35, inconsistent=False, first_words=60, final_prefix="second"):
    settings = Settings(data_dir=tmp_path, demo_mode=False, mesh_api_key="test-no-network")
    store = Store(tmp_path)
    seed_demo(store)
    run = create_run(store, settings, {"brand_id": "brand-ada", "brief": "Explain a concrete test in at most 35 words.", "mode": "live", "use_learning": False})
    contract = validate_contract({"max_words": 35})
    # Freeze independently of the HTTP integration under test in the root task.
    store.patch("runs", run["id"], {"contract": contract})
    store.patch("posts", run["post_id"], {"contract": contract})
    calls = []
    revisions = 0

    async def answer(_client, system, user, schema, temperature=0.2, cache=True):
        nonlocal revisions
        payload = json.loads(user)
        calls.append((schema.__name__, payload))
        assert payload["brief_contract"] == contract
        if schema.__name__ == "SelectedStrategy":
            return schema.model_validate({"angle": "Test a specific ambiguous request", "hook": run["selected_hook"], "audience": "AI engineers", "outline": ["Name the failure", "Describe a test", "Explain its limits"], "reason": "Follow the explicit contract and preserve a concrete example."})
        if schema.__name__ == "PolicyDraft":
            return schema.model_validate({"title": "A concrete test", "content": _content("original", 90)})
        if schema.__name__ == "InitialReview":
            return schema.model_validate(_demo_review(0))
        if schema.__name__ == "RefinementReview":
            review = _demo_review(1)
            for criterion in review["criteria"]:
                criterion["score"] = 5
            if inconsistent and revisions == 1:
                review["requests"] = [{"issue": "The example could be clearer.", "instruction": "Clarify the specific input that triggers the example."}]
            return schema.model_validate(review)
        if schema.__name__ == "SubstantiveRevision":
            revisions += 1
            return schema.model_validate({"title": "A concrete test", "content": _content("first", first_words) if revisions == 1 else _content(final_prefix, final_words), "addressed_requests": ["Shortened the concrete example and retained its intended behavior."]})
        raise AssertionError(schema.__name__)

    monkeypatch.setattr(MeshClient, "complete_json", answer)
    asyncio.run(run_pipeline(run["id"], store, settings))
    return store, run, calls


@pytest.mark.parametrize("inconsistent", [False, True])
def test_high_editor_score_cannot_erase_constraint_and_forces_bounded_repair(tmp_path, monkeypatch, inconsistent):
    store, run, calls = _run(tmp_path, monkeypatch, inconsistent=inconsistent)
    saved = store.get("runs", run["id"])
    post = store.get("posts", run["post_id"])
    assert saved["status"] == "complete", saved.get("error")
    assert post["status"] == "draft"
    assert len(post["versions"]) == len(post["reviews"]) == 3
    first_review = post["reviews"][1]
    assert all(item["score"] == 5 for item in first_review["criteria"])
    assert first_review["raw_model_review"]["approved"] is True
    assert first_review["approved"] is False
    assert first_review["contract_checks"]["passed"] is False
    assert first_review["contract_requests"]
    assert post["contract_checks"]["passed"] is True
    assert post["versions"][0]["content"] == post["original_draft"] == _content("original", 90)
    assert [version["contract_checks"]["counts"]["words"] for version in post["versions"]] == [90, 60, 35]
    repairs = [payload for name, payload in calls if name == "SubstantiveRevision"]
    assert len(repairs) == 2
    assert repairs[-1]["contract_checks"]["counts"]["words"] == 60


def test_unresolved_contract_stops_at_bound_with_raw_scores_and_needs_review(tmp_path, monkeypatch):
    store, run, calls = _run(tmp_path, monkeypatch, final_words=50)
    post = store.get("posts", run["post_id"])
    assert store.get("runs", run["id"])["status"] == "complete"
    assert post["status"] == "needs_review"
    assert len(post["versions"]) == 3
    assert len([name for name, _ in calls if name == "SubstantiveRevision"]) == 2
    assert post["contract_checks"]["passed"] is False
    assert post["reviews"][-1]["raw_model_review"]["approved"] is True
    assert post["reviews"][-1]["approved"] is False


def test_one_word_contract_repair_is_allowed_after_substantive_revision(tmp_path, monkeypatch):
    store, run, _ = _run(tmp_path, monkeypatch, first_words=36, final_prefix="first")
    post = store.get("posts", run["post_id"])
    assert store.get("runs", run["id"])["status"] == "complete"
    assert post["contract_checks"]["passed"] is True
    assert len(post["versions"]) == 3
    assert any(event["choice"] == "Focused contract repair 2 saved" for event in store.list("events", post_id=post["id"]))


def test_manual_review_recalculates_same_frozen_contract_without_rewriting(tmp_path, monkeypatch):
    post = {"title": "A concrete test", "content": _content("manual", 45), "contract": {"max_words": 35}}
    original = dict(post)

    async def answer(_client, system, user, schema, temperature=0, **kwargs):
        payload = json.loads(user)
        assert payload["contract_checks"]["counts"]["words"] == 45
        return schema.model_validate(_demo_review(1))

    monkeypatch.setattr(MeshClient, "complete_json", answer)
    review = asyncio.run(review_post(post, {}, Settings(data_dir=tmp_path, mesh_api_key="test-no-network"), "live"))
    assert post == original
    assert review["approved"] is False
    assert review["raw_model_review"]["approved"] is True
    assert review["contract_checks"] == check_contract(post["content"], post["contract"])


def test_demo_reports_real_contract_failure_without_claiming_a_model_repair(tmp_path):
    settings = Settings(data_dir=tmp_path, demo_mode=True)
    store = Store(tmp_path)
    seed_demo(store)
    run = create_run(store, settings, {"brand_id": "brand-ada", "brief": "Explain AI testing", "mode": "demo", "use_learning": False})
    store.patch("runs", run["id"], {"contract": {"max_words": 35}})
    store.patch("posts", run["post_id"], {"contract": {"max_words": 35}})
    asyncio.run(run_pipeline(run["id"], store, settings))
    post = store.get("posts", run["post_id"])
    assert store.get("runs", run["id"])["status"] == "complete"
    assert post["status"] == "needs_review"
    assert len(post["versions"]) == 2
    assert post["contract_checks"]["passed"] is False
    assert any(event["choice"] == "Demo fixture requires manual correction" for event in store.list("events", post_id=post["id"]))


@pytest.fixture
def contract_api(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path, worker_enabled=False))) as client:
        yield client


def test_api_freezes_canonical_contract_on_run_and_post(contract_api):
    payload = {"brand_id": "brand-ada", "brief": "Explain a useful testing practice.", "mode": "demo",
               "contract": {"max_words": 150, "required_sections": ["  Try   it:  "], "plain_text": True}}
    response = contract_api.post("/api/runs", json=payload)
    assert response.status_code == 202, response.text
    run = response.json()
    expected = {"max_words": 150, "required_sections": ["Try it"], "plain_text": True}
    assert run["contract"] == expected
    payload["contract"]["required_sections"].append("Changed after submission")
    fetched = contract_api.get(f"/api/runs/{run['id']}").json()["run"]
    assert fetched["contract"] == expected
    assert contract_api.get(f"/api/posts/{run['post_id']}").json()["contract"] == expected
    assert fetched["manifest"]["contract_version"] == "brief-contract-v1"
    assert "BriefContract" in fetched["manifest"]["schema_hashes"]


@pytest.mark.parametrize("platform,contract", [
    ("newsletter", {"max_words": 150}),
    ("linkedin", {"max_characters": 3001}),
    ("linkedin", {"min_words": 200, "max_words": 100}),
    ("linkedin", {"max_words": True}),
])
def test_api_invalid_contract_does_not_reserve_any_run_or_post(contract_api, platform, contract):
    store = contract_api.app.state.store
    before = {collection: store.list(collection) for collection in ("runs", "posts", "events")}
    response = contract_api.post("/api/runs", json={"brand_id": "brand-ada", "brief": "Explain a useful testing practice.",
                                "mode": "demo", "platform": platform, "contract": contract})
    assert response.status_code in {400, 422}, response.text
    assert {collection: store.list(collection) for collection in before} == before


def _api_failed_contract(client):
    response = client.post("/api/runs", json={"brand_id": "brand-ada", "brief": "Explain a useful testing practice.",
                           "mode": "demo", "contract": {"max_words": 35}})
    assert response.status_code == 202, response.text
    run = response.json()
    asyncio.run(run_pipeline(run["id"], client.app.state.store, client.app.state.settings))
    endpoint = f"/api/posts/{run['post_id']}"
    assert client.get(endpoint).json()["contract_checks"]["passed"] is False
    return endpoint, run


@pytest.mark.parametrize("acknowledge", [False, True])
def test_api_contract_failure_cannot_be_overridden_by_acknowledgement(contract_api, acknowledge):
    endpoint, run = _api_failed_contract(contract_api)
    store = contract_api.app.state.store
    original = store.get("posts", run["post_id"])
    response = contract_api.post(endpoint + "/approve", json={"acknowledge_unresolved": acknowledge})
    assert response.status_code == 409
    assert "brief contract" in response.json()["detail"]
    assert store.get("posts", run["post_id"]) == original


def test_api_manual_edit_resolves_contract_and_preserves_historical_checks(contract_api):
    endpoint, run = _api_failed_contract(contract_api)
    before = contract_api.get(endpoint).json()
    history = deepcopy(before["versions"])
    reviews = deepcopy(before["reviews"])
    response = contract_api.post(endpoint + "/edit", json={"content": _content("edited", 30),
                                "reason": "Shorten the draft to satisfy the confirmed word limit."})
    assert response.status_code == 200, response.text
    edited = response.json()
    checks = check_contract(edited["content"], edited["contract"])
    assert checks["passed"] is True
    assert edited["contract_checks"] == checks == edited["versions"][-1]["contract_checks"]
    assert checks["content_sha256"] != before["contract_checks"]["content_sha256"]
    assert edited["versions"][:-1] == history
    assert edited["reviews"] == reviews
    assert edited["original_draft"] == before["original_draft"]
    assert edited["review_stale"] and edited["status"] == "needs_review"
    # Passing deterministic checks does not erase outstanding editorial concerns.
    assert contract_api.post(endpoint + "/approve").status_code == 409
    approved = contract_api.post(endpoint + "/approve", json={"acknowledge_unresolved": True})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["versions"][:-1] == history
    assert contract_api.get(f"/api/runs/{run['id']}").json()["run"]["contract"] == before["contract"]


def test_api_read_and_approval_recompute_checks_instead_of_trusting_a_stale_hash(contract_api):
    endpoint, run = _api_failed_contract(contract_api)
    store = contract_api.app.state.store
    old_checks = check_contract(_content("oldvalid", 30), {"max_words": 35})
    store.patch("posts", run["post_id"], {"content": _content("newinvalid", 45), "contract_checks": old_checks})
    current = contract_api.get(endpoint).json()
    assert current["contract_checks"]["counts"]["words"] == 45
    assert current["contract_checks"]["passed"] is False
    assert current["contract_checks"]["content_sha256"] != old_checks["content_sha256"]
    assert contract_api.post(endpoint + "/approve", json={"acknowledge_unresolved": True}).status_code == 409
    assert store.get("posts", run["post_id"])["status"] == "needs_review"

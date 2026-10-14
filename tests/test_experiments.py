"""Experiment integrity, missing outcomes and comparable-cohort regressions."""
from collections import Counter
from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.creatoros.config import Settings
from backend.creatoros.experiments import (
    ExperimentInput, analyze_experiment, assignment_for_run, bind_run, build_router,
    create_comparison, create_experiment, experiment_report, list_experiments, prepare_binding,
)
from backend.creatoros.learning import HOOKS
from backend.creatoros.store import Store, utcnow


@pytest.fixture
def store(tmp_path):
    db = Store(tmp_path)
    db.put("brands", {"id": "voice", "profile": {"tone": "Plain, calm and concrete"}, "profile_version": 3})
    yield db
    db.close()


def register(store, **changes):
    return create_experiment(store, {"brand_id": "voice", "name": "Opening comparison",
                                    "hypothesis": "Problem-led openings may receive more useful discussion.", **changes})


def reserve(store, experiment, slot, **changes):
    assignment = assignment_for_run(store, experiment["id"], slot["id"])
    if assignment["existing_run_id"]:
        return store.get("runs", assignment["existing_run_id"])
    stamp = utcnow()
    run = {**assignment, "id": str(uuid4()), "post_id": str(uuid4()), "created_at": stamp,
           "status": "queued", "mode": "demo" if assignment["feedback_source"] == "simulated" else "live",
           "brief": "Explain one useful engineering workflow with a concrete example.", **changes}
    if "manifest" in assignment:
        run.update({key: assignment[key] for key in ("brief", "mode", "contract", "manifest")})
        run["model_preset"] = assignment["model_preset"] or "configured"
    store.put("posts", {"id": run["post_id"], "run_id": run["id"], "brand_id": "voice", "hook": run["selected_hook"],
                        "platform": run["platform"], "created_at": stamp, "status": "generating", "content": "",
                        "published_at": None, "is_demo": run["mode"] == "demo"})
    store.put("runs", run)
    bind_run(store, experiment["id"], slot["id"], run)
    return run


def publish_and_observe(store, run, **changes):
    store.patch("runs", run["id"], {"status": "complete"})
    store.patch("posts", run["post_id"], {"status": "published_manually", "published_at": utcnow(),
                                        "title": "A concrete post", "content": "An actual opening.\nA useful explanation."})
    value = {"id": str(uuid4()), "revision_id": str(uuid4()), "post_id": run["post_id"], "source": run["feedback_source"],
             "window": run["window"], "impressions": 100, "comments": {HOOKS[0]: 5, HOOKS[1]: 1, HOOKS[2]: 0}[run["selected_hook"]],
             "reposts": 0, "timing_status": "window_matched", "captured_at": utcnow(), **changes}
    store.put("feedback", value)
    return value


def test_registration_balances_each_block_freezes_profile_and_does_not_activate_baseline(store):
    first = register(store)
    assert Counter(slot["hook"] for slot in first["slots"]) == {hook: 3 for hook in HOOKS}
    for start in range(0, 9, 3):
        assert {slot["hook"] for slot in first["slots"][start:start + 3]} == set(HOOKS)
    assert first["counts"]["pending"] == 9
    assert "randomization_seed" not in first
    assert "profile" not in first
    assert store.list("snapshots") == []
    store.patch("brands", "voice", {"profile": {"tone": "Loud"}, "profile_version": 4})
    frozen = assignment_for_run(store, first["id"], first["slots"][0]["id"])
    assert frozen["profile"] == {"tone": "Plain, calm and concrete"}
    assert frozen["profile_version"] == 3
    assert frozen["learning_snapshot_id"] is None
    assert not frozen["use_learning"]
    assert frozen["experiment_baseline_snapshot"] == first["baseline_snapshot"]
    assert list_experiments(store, "other") == []


@pytest.mark.parametrize("changes", [{"slots_per_hook": 0}, {"slots_per_hook": 11}, {"slots_per_hook": True},
                                     {"window": "cumulative"}, {"source": "real"}, {"platform": "other"},
                                     {"post_id": "existing-published"}, {"hypothesis": "          "}])
def test_registration_rejects_ambiguous_or_retrospective_inputs(changes):
    with pytest.raises(ValidationError):
        ExperimentInput.model_validate({"brand_id": "voice", "name": "Valid name", "hypothesis": "A useful hypothesis.", **changes})


def test_binding_preserves_failed_assignment_and_rejects_new_run(store):
    experiment = register(store)
    slot = experiment["slots"][0]
    first = reserve(store, experiment, slot)
    store.patch("runs", first["id"], {"status": "failed", "error": "Transport interrupted"})
    assert reserve(store, experiment, slot)["id"] == first["id"]
    second = {**first, "id": str(uuid4())}
    store.put("runs", second)
    with pytest.raises(ValueError, match="already bound"):
        bind_run(store, experiment["id"], slot["id"], second)
    report = experiment_report(store, experiment["id"])
    assert report["slots"][0]["status"] == "failed"
    assert report["counts"]["pending"] == 8


@pytest.mark.parametrize("change", ["past", "published", "outcome", "profile", "hook", "source"])
def test_existing_or_changed_runs_cannot_be_attached(store, change):
    experiment = register(store)
    slot = experiment["slots"][0]
    # Prepare a prospective run, then simulate a caller attempting to attach a
    # historical/favorable artifact or change the fixed assignment.
    assignment = assignment_for_run(store, experiment["id"], slot["id"])
    stamp = utcnow()
    run = {**assignment, "id": "candidate", "post_id": "candidate-post", "created_at": stamp, "status": "queued", "mode": "demo"}
    post = {"id": "candidate-post", "status": "generating", "created_at": stamp, "content": "", "published_at": None}
    if change == "past":
        run["created_at"] = "2000-01-01T00:00:00+00:00"
    elif change == "published":
        post["published_at"] = stamp
    elif change == "outcome":
        store.put("feedback", {"id": "already-seen", "post_id": "candidate-post", "comments": 999})
    elif change == "profile":
        run["profile"] = {"tone": "A new voice"}
    elif change == "hook":
        run["selected_hook"] = next(hook for hook in HOOKS if hook != slot["hook"])
    elif change == "source":
        run["mode"] = "live"
    store.put("posts", post)
    store.put("runs", run)
    with pytest.raises(ValueError):
        bind_run(store, experiment["id"], slot["id"], run)


def test_analysis_retains_missing_failed_and_excluded_slots_instead_of_dropping_them(store):
    experiment = register(store, source="manual")
    slots = experiment["slots"]
    runs = [reserve(store, experiment, slot) for slot in slots[:5]]
    publish_and_observe(store, runs[0])
    publish_and_observe(store, runs[1], source="simulated")
    publish_and_observe(store, runs[2], timing_status="unverified")
    store.patch("runs", runs[3]["id"], {"status": "failed", "error": "No response"})
    store.patch("runs", runs[4]["id"], {"status": "complete"})
    analysis = analyze_experiment(store, experiment["id"])
    assert len(analysis["slots"]) == 9
    assert len(analysis["evidence"]) == 1
    assert len(analysis["excluded"]) == 8
    assert analysis["counts"] == {"pending": 4, "queued": 0, "running": 0, "failed": 1, "interrupted": 0,
                                  "awaiting_publish": 1, "awaiting_observation": 0, "excluded": 2, "eligible": 1}
    assert analysis["status"] == "inconclusive"
    assert analysis["preferred_hook"] is None


def test_complete_cohort_uses_assigned_posts_only_and_saved_analyses_do_not_change(store):
    experiment = register(store)
    observations = []
    for slot in experiment["slots"]:
        observations.append(publish_and_observe(store, reserve(store, experiment, slot)))
    store.put("posts", {"id": "unassigned", "brand_id": "voice", "platform": "linkedin", "hook": "question-first", "status": "published"})
    store.put("feedback", {"id": "irrelevant", "post_id": "unassigned", "source": "simulated", "window": "24h", "impressions": 1, "comments": 999})
    first = analyze_experiment(store, experiment["id"])
    assert first["status"] == "descriptive_signal"
    assert first["preferred_hook"] == "problem-first"
    assert first["complete_cohort"]
    assert len(first["evidence"]) == 9
    assert "irrelevant" not in first["evidence_ids"]
    assert all(item["impressions"] == 300 for item in first["stats"])
    for observation in observations:
        store.patch("feedback", observation["id"], {"comments": 1, "revision_id": str(uuid4())})
    before_reanalysis = experiment_report(store, experiment["id"])
    assert before_reanalysis["latest_analysis"] == first
    second = analyze_experiment(store, experiment["id"])
    assert second["version"] == 2
    assert second["status"] == "inconclusive"
    assert store.get("experiment_analyses", first["id"]) == first
    assert first["evidence_ids"] != second["evidence_ids"]


def test_workflow_pilot_cannot_claim_a_preference_even_with_separated_rates(store):
    experiment = register(store, slots_per_hook=1)
    for slot in experiment["slots"]:
        publish_and_observe(store, reserve(store, experiment, slot), impressions=1000)
    analysis = analyze_experiment(store, experiment["id"])
    assert analysis["complete_cohort"]
    assert analysis["status"] == "inconclusive"
    assert analysis["preferred_hook"] is None
    assert "workflow pilot" in analysis["explanation"]


def test_incomplete_cohort_cannot_declare_preference_after_enough_favorable_results(store):
    experiment = register(store, slots_per_hook=4)
    for slot in experiment["slots"][:9]:
        publish_and_observe(store, reserve(store, experiment, slot))
    analysis = analyze_experiment(store, experiment["id"])
    assert all(item["sufficient"] for item in analysis["stats"])
    assert analysis["preferred_hook"] is None
    assert analysis["status"] == "inconclusive"


def test_plan_tampering_is_detected(store):
    experiment = register(store)
    stored = store.get("experiments", experiment["id"])
    stored["slots"][0]["hook"] = "a-favorable-new-condition"
    store.put("experiments", stored)
    with pytest.raises(ValueError, match="registration has changed"):
        analyze_experiment(store, experiment["id"])


def test_matched_pair_freezes_inputs_models_and_profile_and_never_enters_experiment_stats(store, tmp_path):
    experiment = register(store)
    settings = Settings(data_dir=tmp_path, chat_model="model-at-registration")
    payload = {"brief": "Explain an engineering decision with one concrete example.", "mode": "demo", "model_preset": "budget"}
    pair = create_comparison(store, settings, experiment["id"], payload)
    assert pair == create_comparison(store, replace(settings, chat_model="changed"), experiment["id"], payload)
    assert not pair["policy_contrast"]  # No prior signal, so both rotate to the same first hook.
    with pytest.raises(ValueError, match="already has a fixed comparison"):
        create_comparison(store, settings, experiment["id"], {**payload, "brief": "A different topic chosen after seeing the first draft."})
    assignments = [assignment_for_run(store, experiment["id"], branch["id"]) for branch in pair["branches"]]
    for key in ("brief", "profile", "profile_version", "contract", "manifest", "model_preset"):
        assert assignments[0][key] == assignments[1][key]
    assert [value["use_learning"] for value in assignments] == [False, True]
    runs = [reserve(store, experiment, branch) for branch in pair["branches"]]
    for run in runs:
        publish_and_observe(store, run)
    analysis = analyze_experiment(store, experiment["id"])
    assert not analysis["evidence"]
    assert analysis["counts"]["pending"] == 9
    report = experiment_report(store, experiment["id"])
    assert len(report["comparison"]["branches"]) == 2
    assert all(branch["opening"] == "An actual opening." for branch in report["comparison"]["branches"])


def test_comparison_detects_modified_frozen_inputs(store, tmp_path):
    experiment = register(store)
    create_comparison(store, Settings(data_dir=tmp_path), experiment["id"], {"brief": "Explain a repeatable engineering workflow."})
    stored = store.get("experiments", experiment["id"])
    stored["comparison"]["brief"] = "Choose a more favorable example."
    store.put("experiments", stored)
    with pytest.raises(ValueError, match="paired comparison has changed"):
        experiment_report(store, experiment["id"])


def test_router_enforces_scope_preserves_existing_run_and_serves_frozen_history(store, tmp_path):
    app = FastAPI()
    app.state.store = store
    app.state.settings = Settings(data_dir=tmp_path)

    def create(store, settings, body):
        return reserve(store, {"id": body["experiment_id"]}, {"id": body["experiment_slot_id"]}, brief=body["brief"])

    app.include_router(build_router(create))
    with TestClient(app) as client:
        result = client.post("/api/experiments", json={"brand_id": "voice", "name": "A first experiment", "hypothesis": "A clear problem may invite specific discussion."})
        assert result.status_code == 201
        experiment = result.json()
        endpoint = f"/api/experiments/{experiment['id']}"
        slot_path = f"{endpoint}/slots/{experiment['slots'][0]['id']}/run"
        assert client.post(slot_path, json={"brief": "Explain repeatable engineering workflows.", "mode": "live"}).status_code == 409
        first = client.post(slot_path, json={"brief": "Explain repeatable engineering workflows."})
        assert first.status_code == 202
        store.patch("runs", first.json()["id"], {"status": "failed"})
        repeated = client.post(slot_path, json={"brief": "A different topic cannot replace the reserved run."})
        assert repeated.json()["id"] == first.json()["id"]
        assert repeated.json()["brief"] == first.json()["brief"]
        analysis = client.post(f"{endpoint}/analyze", json={}).json()
        assert client.get(f"{endpoint}/analyses/{analysis['id']}").json() == analysis
        assert client.get(f"{endpoint}/analyses/wrong").status_code == 404
        assert client.get("/api/experiments?brand_id=voice").json()[0]["id"] == experiment["id"]
        assert client.post(f"{endpoint}/slots/missing/run", json={"brief": "Explain a clear workflow."}).status_code == 404
        assert client.get("/api/experiments/missing").status_code == 404


def test_router_partial_pair_failure_keeps_same_pair_and_only_missing_branch_retries(store, tmp_path):
    app = FastAPI()
    app.state.store = store
    app.state.settings = Settings(data_dir=tmp_path)
    attempts = []
    fail = [True]

    def create(store, settings, body):
        attempts.append(body["experiment_slot_id"])
        if len(attempts) == 2 and fail[0]:
            raise ValueError("Temporary reservation failure")
        return reserve(store, {"id": body["experiment_id"]}, {"id": body["experiment_slot_id"]})

    app.include_router(build_router(create))
    experiment = register(store)
    with TestClient(app) as client:
        endpoint = f"/api/experiments/{experiment['id']}/comparisons"
        payload = {"brief": "Explain how to preserve an auditable engineering decision."}
        assert client.post(endpoint, json=payload).status_code == 409
        saved = experiment_report(store, experiment["id"])["comparison"]
        assert saved["branches"][0]["run_id"]
        assert saved["branches"][1]["run_id"] is None
        fail[0] = False
        completed = client.post(endpoint, json=payload)
        assert completed.status_code == 202
        assert completed.json()["id"] == saved["id"]
        assert completed.json()["branches"][0]["run_id"] == saved["branches"][0]["run_id"]
        assert len(store.list("runs")) == 2
        assert len(attempts) == 3


def test_real_service_uses_registration_profile_and_slot_assignment_even_after_brand_changes(store, tmp_path):
    from backend.creatoros.service import create_run
    experiment = register(store)
    slot = experiment["slots"][0]
    store.patch("brands", "voice", {"profile": {"tone": "Different after registration"}, "profile_version": 4})
    body = {"brand_id": "voice", "brief": "Explain how a repeatable process helps useful evaluation.", "mode": "demo",
            "experiment_id": experiment["id"], "experiment_slot_id": slot["id"], "contract": {"max_words": 150}}
    run = create_run(store, Settings(data_dir=tmp_path), body)
    assert run["selected_hook"] == slot["hook"]
    assert run["profile_version"] == 3
    assert run["profile"]["tone"] == "Plain, calm and concrete"
    assert run["contract"]["max_words"] == 150
    assert store.get("posts", run["post_id"])["experiment_id"] == experiment["id"]
    assert create_run(store, Settings(data_dir=tmp_path), {**body, "brief": "A replacement must not create a new draft."})["id"] == run["id"]
    assert len(store.list("runs")) == 1


def test_real_app_matched_pair_uses_same_canonical_contract_models_profile_and_frozen_baseline(tmp_path):
    from backend.creatoros.main import create_app
    with TestClient(create_app(Settings(data_dir=tmp_path, worker_enabled=False))) as client:
        experiment = client.post("/api/experiments", json={
            "brand_id": "brand-ada", "name": "Measure openings", "hypothesis": "Outcome-led openings may invite more discussion."}).json()
        endpoint = f"/api/experiments/{experiment['id']}/comparisons"
        body = {"brief": "Explain a repeatable evaluation workflow with a useful concrete example.", "model_preset": "budget"}
        response = client.post(endpoint, json=body)
        assert response.status_code == 202, response.text
        pair = response.json()
        runs = [client.get(f"/api/runs/{branch['run_id']}").json()["run"] for branch in pair["branches"]]
        assert len({run["id"] for run in runs}) == 2
        for key in ("brief", "contract", "profile", "profile_version", "manifest", "model_preset", "platform"):
            assert runs[0][key] == runs[1][key]
        assert runs[0]["contract"] == {"required_sections": [], "plain_text": False}
        assert runs[0]["selected_hook"] == "problem-first"
        assert runs[1]["selected_hook"] == experiment["baseline_snapshot"]["preferred_hook"] == "outcome-first"
        assert pair["policy_contrast"]
        # An exact retry does not reserve extra generation or change the pair.
        again = client.post(endpoint, json=body)
        assert again.status_code == 202
        assert [branch["run_id"] for branch in again.json()["branches"]] == [run["id"] for run in runs]
        assert client.post(endpoint, json={**body, "contract": {"max_words": 100}}).status_code == 409


def test_real_service_rebinds_a_durably_saved_reservation_without_an_extra_run(store, tmp_path):
    from backend.creatoros.service import create_run
    experiment = register(store)
    slot = experiment["slots"][0]
    body = {"brand_id": "voice", "brief": "Explain one useful engineering workflow.", "mode": "demo",
            "experiment_id": experiment["id"], "experiment_slot_id": slot["id"]}
    run = create_run(store, Settings(data_dir=tmp_path), body)
    stored = store.get("experiments", experiment["id"])
    stored["slots"][0].update(run_id=None, post_id=None)
    store.put("experiments", stored)
    recovered = create_run(store, Settings(data_dir=tmp_path), body)
    assert recovered["id"] == run["id"]
    assert experiment_report(store, experiment["id"])["slots"][0]["run_id"] == run["id"]
    assert len(store.list("runs")) == 1


def test_matched_demo_branches_complete_with_distinct_actual_openings_and_no_ai_calls(tmp_path, monkeypatch):
    import asyncio
    from backend.creatoros.main import create_app
    from backend.creatoros.mesh import MeshClient
    from backend.creatoros.pipeline import run_pipeline

    async def forbidden_ai(*args, **kwargs):
        pytest.fail("Demo experiment comparison must not call a paid model.")

    monkeypatch.setattr(MeshClient, "complete_json", forbidden_ai)
    settings = Settings(data_dir=tmp_path, worker_enabled=False)
    with TestClient(create_app(settings)) as client:
        experiment = client.post("/api/experiments", json={
            "brand_id": "brand-ada", "name": "Demo comparison", "hypothesis": "Outcome-led openings may produce more specific discussion."}).json()
        pair = client.post(f"/api/experiments/{experiment['id']}/comparisons", json={
            "brief": "Explain repeatable AI evaluation with a concrete example and actionable next step."}).json()
        for branch in pair["branches"]:
            asyncio.run(run_pipeline(branch["run_id"], client.app.state.store, settings))
        report = client.get(f"/api/experiments/{experiment['id']}").json()
        branches = report["comparison"]["branches"]
        assert all(branch["status"] == "awaiting_publish" for branch in branches)
        assert all(branch["content"] for branch in branches)
        assert branches[0]["opening"] != branches[1]["opening"]
        assert report["counts"]["pending"] == 9


def test_prepare_binding_validates_without_persisting_run_post_or_assignment(store):
    experiment = register(store)
    slot = experiment["slots"][0]
    assignment = assignment_for_run(store, experiment["id"], slot["id"])
    run = {**assignment, "id": "pending-run", "post_id": "pending-post", "status": "queued", "mode": "demo", "created_at": utcnow()}
    post = {"id": "pending-post", "run_id": "pending-run", "brand_id": "voice", "hook": slot["hook"],
            "status": "generating", "content": "", "published_at": None, "platform": "linkedin", "created_at": run["created_at"]}
    prepared = prepare_binding(store, experiment["id"], slot["id"], run, post)
    assert prepared["slots"][0]["run_id"] == "pending-run"
    assert store.get("experiments", experiment["id"])["slots"][0]["run_id"] is None
    assert store.list("runs") == store.list("posts") == store.list("events") == []


def test_service_reserves_post_run_assignment_and_audit_event_in_one_batch(store, tmp_path, monkeypatch):
    from backend.creatoros.service import create_run
    experiment = register(store)
    batches = []
    original = store.put_many

    def record(records):
        batches.append(records)
        return original(records)

    monkeypatch.setattr(store, "put_many", record)
    run = create_run(store, Settings(data_dir=tmp_path), {
        "brand_id": "voice", "brief": "Explain a concrete repeatable engineering workflow.", "mode": "demo",
        "experiment_id": experiment["id"], "experiment_slot_id": experiment["slots"][0]["id"]})
    assert len(batches) == 1
    assert {collection for collection, _ in batches[0]} == {"posts", "runs", "experiments", "events"}
    saved = store.get("experiments", experiment["id"])["slots"][0]
    assert saved["run_id"] == run["id"]
    assert saved["post_id"] == run["post_id"]
    assert any(event["node"] == "experiment" for event in store.list("events", post_id=run["post_id"]))


@pytest.mark.parametrize("comparison", [False, True])
def test_reservation_database_failure_rolls_back_run_post_and_binding_without_orphans(store, tmp_path, comparison):
    from sqlalchemy import event
    from backend.creatoros.service import create_run
    experiment = register(store)
    settings = Settings(data_dir=tmp_path)
    brief = "Explain a concrete repeatable engineering workflow."
    slot_id = experiment["slots"][0]["id"]
    if comparison:
        pair = create_comparison(store, settings, experiment["id"], {"brief": brief})
        slot_id = pair["branches"][0]["id"]
    inserts = []

    def fail_mid_transaction(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT"):
            inserts.append(statement)
            if len(inserts) == 3:
                raise RuntimeError("Simulated crash after post and run inserts")

    body = {"brand_id": "voice", "brief": brief, "mode": "demo", "experiment_id": experiment["id"], "experiment_slot_id": slot_id}
    event.listen(store.engine, "before_cursor_execute", fail_mid_transaction)
    try:
        with pytest.raises(RuntimeError, match="Simulated crash"):
            create_run(store, settings, body)
    finally:
        event.remove(store.engine, "before_cursor_execute", fail_mid_transaction)
    assert len(inserts) == 3
    assert store.list("posts") == store.list("runs") == store.list("events") == []
    assert assignment_for_run(store, experiment["id"], slot_id)["existing_run_id"] is None
    retried = create_run(store, settings, body)
    assert assignment_for_run(store, experiment["id"], slot_id)["existing_run_id"] == retried["id"]
    assert len(store.list("runs")) == len(store.list("posts")) == 1


def test_pair_ignores_requested_images_and_keeps_recorded_model_when_runtime_configuration_changes(store, tmp_path):
    from backend.creatoros.service import create_run
    experiment = register(store, source="manual")
    frozen_settings = Settings(data_dir=tmp_path, mesh_api_key="unused-reservation-only", chat_model="openai/frozen-model")
    brief = "Explain one useful engineering workflow with a concrete next step."
    pair = create_comparison(store, frozen_settings, experiment["id"], {"brief": brief, "mode": "live"})
    for branch in pair["branches"]:
        run = create_run(store, replace(frozen_settings, chat_model="openai/later-model"), {
            "brand_id": "voice", "brief": "A changed client brief is ignored for this frozen pair.", "mode": "live",
            "generate_image": True, "experiment_id": experiment["id"], "experiment_slot_id": branch["id"]})
        assert run["brief"] == brief
        assert run["generate_image"] is False
        assert run["model"] == run["manifest"]["chat_model"] == "openai/frozen-model"

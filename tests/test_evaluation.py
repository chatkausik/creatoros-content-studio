"""Guard honest scoring and the controlled feedback comparison."""
import argparse
import asyncio
import copy
import json
import random

import pytest

from scripts.evaluate import classify_openings, evaluate, judge_pair, summarize


def test_fixture_evaluation_is_unscored_and_ablations_are_matched(tmp_path, monkeypatch):
    from backend.creatoros.mesh import MeshClient

    async def reject_ai(*args, **kwargs):
        raise AssertionError("Fixture evaluation must never make an AI call")

    monkeypatch.setattr(MeshClient, "complete_json", reject_ai)
    monkeypatch.setattr(MeshClient, "generate_image", reject_ai)
    code = asyncio.run(evaluate(argparse.Namespace(live=False, output=tmp_path, seed=2026)))
    result = json.loads((tmp_path / "results.json").read_text())
    assert code == 0
    assert result["status"] == "fixture"
    assert result["summary"]["pairs"] == 8
    assert result["summary"]["changed_pairs"] == 8
    assert result["summary"]["scored_pairs"] == 0
    assert result["summary"]["mean_delta"] is None
    assert all(case["scores"] is None for case in result["cases"])
    for pair in result["ablations"]:
        baseline, learned = pair["baseline_run"], pair["learned_run"]
        assert baseline["profile"] == learned["profile"]
        assert baseline["brief"] == learned["brief"]
        assert baseline["feedback_source"] == learned["feedback_source"] == "simulated"
        assert baseline["window"] == learned["window"] == "24h"
        assert baseline["use_learning"] is False
        assert learned["use_learning"] is True
        assert baseline["learning_snapshot_id"] is None
        assert learned["learning_snapshot_id"] is not None
        assert pair["baseline_hook"] == "problem-first"
        assert pair["learned_hook"] == "outcome-first"


def test_judge_unblinds_both_candidate_orders():
    class IndependentJudge:
        orders = []

        async def complete_json(self, system, user, schema, **kwargs):
            payload = json.loads(user)
            self.orders.append(payload["candidate_a"])
            assert "original" not in payload
            assert "revision" not in payload
            scores = {}
            for candidate in ("candidate_a", "candidate_b"):
                value = 2 if payload[candidate] == "Weak draft." else 4
                scores[candidate] = {"brief_fulfillment": value, "specificity": value,
                                     "clarity": value, "brand_fit": value, "rationale": "Evidence.", "opening_type": "unclear"}
            return schema.model_validate(scores)

    judge = IndependentJudge()
    for seed in range(10):
        result = asyncio.run(judge_pair(judge, "Write clearly.", {"tone": "direct"},
                                        "Weak draft.", "Strong draft.", random.Random(seed)))
        assert result["mean_before"] == 2
        assert result["mean_after"] == 4
        assert result["delta"] == 2
    assert set(judge.orders) == {"Weak draft.", "Strong draft."}


def test_summary_retains_regressions_and_excludes_unscored_cases():
    cases = []
    for before, after in ((2, 4), (5, 3), (3, 3)):
        dimensions_before = {name: before for name in ("brief_fulfillment", "specificity", "clarity", "brand_fit")}
        dimensions_after = {name: after for name in dimensions_before}
        cases.append({"scores": {"before": dimensions_before, "after": dimensions_after,
                                 "mean_before": before, "mean_after": after, "delta": after - before}})
    cases.append({"scores": None, "error": "Judge unavailable"})
    summary = summarize(cases)
    assert summary["pairs"] == 4
    assert summary["scored_pairs"] == 3
    assert summary["wins"] == summary["ties"] == summary["losses"] == 1
    assert summary["mean_delta"] == 0
    assert summary["errors"] == 1
    assert summary["completed_pairs"] == 3
    assert summary["completion_rate"] == 0.75
    assert "failures are excluded" in summary["quality_statistics_scope"]


def test_failed_generations_preserve_both_ablation_branches_and_private_diagnostics(tmp_path, monkeypatch):
    from backend.creatoros.config import Settings
    import backend.creatoros.config as config
    import backend.creatoros.pipeline as pipeline

    settings = Settings(data_dir=tmp_path / "private", worker_enabled=False)
    monkeypatch.setattr(config, "load_settings", lambda: settings)

    async def fail_run(run_id, store, run_settings):
        run = store.get("runs", run_id)
        diagnostics = {"schema": "Draft", "attempt": 2, "errors": [{"type": "value_error", "loc": ["content"], "msg": "Plain text is required"}], "diagnostic_id": "test-diagnostic"}
        store.patch("runs", run_id, {"status": "failed", "stage": "writer", "error": "Structured output validation failed", "error_diagnostics": diagnostics})
        store.patch("posts", run["post_id"], {"content": "A partial saved artifact", "original_draft": "A preserved first draft"})
        directory = run_settings.data_dir / "mesh_diagnostics"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{run_id}.json").write_text(json.dumps({"raw_response": "private-rejected-output-marker"}))

    monkeypatch.setattr(pipeline, "run_pipeline", fail_run)
    output = tmp_path / "report"
    code = asyncio.run(evaluate(argparse.Namespace(live=False, output=output, seed=2026)))
    result = json.loads((output / "results.json").read_text())
    assert code == 1
    assert result["summary"]["completion_rate"] == 0
    assert result["summary"]["mean_after"] is None
    for case in result["cases"]:
        assert case["run"]["status"] == "failed"
        assert case["failed_stage"] == "writer"
        assert case["post"]["content"] == "A partial saved artifact"
        assert case["error_diagnostics"]["schema"] == "Draft"
        assert case["scores"] is None
    for ablation in result["ablations"]:
        assert ablation["passed"] is False
        assert set(ablation["branch_errors"]) == {"baseline", "learned"}
        assert ablation["baseline_run"]["stage"] == ablation["learned_run"]["stage"] == "writer"
    assert result["private_diagnostics"]["files_preserved"] == 12
    assert len(list((settings.data_dir / "evaluation_diagnostics").rglob("*.json"))) == 12
    assert "private-rejected-output-marker" not in (output / "results.json").read_text()


def test_opening_classifier_sees_only_first_sentence_and_unblinds_the_result():
    class OpeningJudge:
        async def complete_json(self, system, user, schema, **kwargs):
            payload = json.loads(user)
            assert set(payload) == {"candidate_a", "candidate_b"}
            assert "HIDDEN_CONTINUATION" not in user
            assert "expected_hook" not in user
            assert "rhetorical" in system
            return schema.model_validate({key: {
                "opening_sentence": sentence,
                "opening_type": "question-first" if sentence.endswith("?") else "outcome-first",
                "rationale": "Classified the supplied sentence only.",
            } for key, sentence in payload.items()})

    for seed in (0, 1, 2, 3):
        result = asyncio.run(classify_openings(
            OpeningJudge(), "\nCan an unchecked agent delete the wrong file? HIDDEN_CONTINUATION",
            "Build confidence in every release.\n\nHIDDEN_CONTINUATION", random.Random(seed)))
        assert result["before"]["opening_type"] == "question-first"
        assert result["after"]["opening_type"] == "outcome-first"
        assert result["before"]["opening_sentence"] == "Can an unchecked agent delete the wrong file?"


def test_opening_classifier_rejects_a_nonverbatim_sentence():
    class BadQuoteJudge:
        async def complete_json(self, system, user, schema, **kwargs):
            return schema.model_validate({name: {"opening_sentence": "Invented replacement.", "opening_type": "unclear", "rationale": "Wrong quote."}
                                          for name in ("candidate_a", "candidate_b")})

    with pytest.raises(ValueError, match="exactly"):
        asyncio.run(classify_openings(BadQuoteJudge(), "A real opening.", "Another real opening.", random.Random(2026)))


def test_recovery_reuses_frozen_artifacts_and_only_retries_failed_operations(tmp_path, monkeypatch):
    import backend.creatoros.config as config
    import backend.creatoros.pipeline as pipeline
    import backend.creatoros.service as service
    from backend.creatoros.config import Settings
    from backend.creatoros.mesh import MeshClient

    monkeypatch.setattr(config, "load_settings", lambda: Settings(data_dir=tmp_path / "private", worker_enabled=False))
    real_pipeline, real_review = pipeline.run_pipeline, pipeline._demo_review
    active = {"index": -1}

    def fail_selected_editor(iteration):
        # Fail before the first review, after a saved revision, and in one ablation branch.
        if {0: 0, 1: 1, 10: 0}.get(active["index"]) == iteration:
            raise RuntimeError("Forced validation failure")
        return real_review(iteration)

    async def first_attempt(run_id, store, settings):
        active["index"] += 1
        await real_pipeline(run_id, store, settings)

    async def reject_ai(*args, **kwargs):
        raise AssertionError("Fixture recovery must never call AI")

    monkeypatch.setattr(MeshClient, "complete_json", reject_ai)
    monkeypatch.setattr(MeshClient, "generate_image", reject_ai)
    monkeypatch.setattr(pipeline, "_demo_review", fail_selected_editor)
    monkeypatch.setattr(pipeline, "run_pipeline", first_attempt)
    initial_dir = tmp_path / "initial"
    assert asyncio.run(evaluate(argparse.Namespace(live=False, output=initial_dir, seed=2026))) == 1
    initial_path = initial_dir / "results.json"
    source = json.loads(initial_path.read_text())
    assert source["summary"]["completed_pairs"] == 6
    assert set(source["ablations"][1]["branch_errors"]) == {"baseline"}
    # Semantic failures must also be retained, not retried until a passing answer appears.
    source["ablations"][0].update(passed=False, opening_compliance=False)
    source["learning_checks"][1]["passed"] = False
    initial_path.write_text(json.dumps(source))
    source_bytes = initial_path.read_bytes()
    expected_runs = {source["cases"][0]["run"]["id"], source["cases"][1]["run"]["id"],
                     source["ablations"][1]["baseline_run"]["id"]}
    retried = []

    async def recovered(run_id, store, settings):
        assert run_id in expected_runs
        assert not (settings.data_dir / "checkpoints.sqlite").exists()
        retried.append(run_id)
        frozen = store.get("runs", run_id)
        writer = copy.deepcopy(frozen["artifacts"]["writer"])
        profile = copy.deepcopy(frozen["profile"])
        await real_pipeline(run_id, store, settings)
        after = store.get("runs", run_id)
        assert after["artifacts"]["writer"] == writer
        assert after["profile"] == profile
        assert after["selected_hook"] == frozen["selected_hook"]

    def reject_new_run(*args, **kwargs):
        raise AssertionError("Recovery must preserve original run IDs and frozen decisions")

    monkeypatch.setattr(pipeline, "_demo_review", real_review)
    monkeypatch.setattr(pipeline, "run_pipeline", recovered)
    monkeypatch.setattr(service, "create_run", reject_new_run)
    final_dir = tmp_path / "recovered"
    # Exit remains nonzero because a completed semantic ablation failure is not hidden.
    assert asyncio.run(evaluate(argparse.Namespace(live=False, output=final_dir, seed=2026,
                                                   resume_results=initial_path))) == 1
    result = json.loads((final_dir / "results.json").read_text())
    assert initial_path.read_bytes() == source_bytes
    assert set(retried) == expected_runs and len(retried) == 3
    assert result["summary"]["completed_pairs"] == 8
    assert result["summary"]["mechanical_failures"] == 0
    assert result["recovery"]["initial_summary"] == source["summary"]
    assert result["recovery"]["initial_learning_checks"] == source["learning_checks"]
    for old, new in zip(source["cases"], result["cases"]):
        if old.get("error"):
            assert new["prior_attempts"] == [old]
            assert new["before"] == old["before"]
            assert new["run"]["id"] == old["run"]["id"]
            assert "error" not in new
        else:
            assert new == old
    assert result["ablations"][0] == source["ablations"][0]
    recovered_ablation = result["ablations"][1]
    assert recovered_ablation["passed"]
    assert recovered_ablation["prior_attempts"] == [source["ablations"][1]]
    assert recovered_ablation["learned"] == source["ablations"][1]["learned"]
    assert recovered_ablation["learned_run"] == source["ablations"][1]["learned_run"]
    assert "not an all-successful first pass" in (final_dir / "RESULTS.md").read_text()


def test_recovery_rejects_configuration_changes_before_running(tmp_path, monkeypatch):
    from backend.creatoros.config import Settings
    import backend.creatoros.config as config

    monkeypatch.setattr(config, "load_settings", lambda: Settings(data_dir=tmp_path / "private"))
    source_path = tmp_path / "source.json"
    source_path.write_text(json.dumps({"mode": "live", "config": {}}))
    with pytest.raises(ValueError, match="mode must match"):
        asyncio.run(evaluate(argparse.Namespace(live=False, output=tmp_path, seed=2026, resume_results=source_path)))
    source_path.write_text(json.dumps({"mode": "fixture", "config": {"model": "changed-model"}}))
    with pytest.raises(ValueError, match="changed model"):
        asyncio.run(evaluate(argparse.Namespace(live=False, output=tmp_path, seed=2026, resume_results=source_path)))


def test_recovery_retries_only_missing_judgment_and_preserves_saved_scores(tmp_path, monkeypatch):
    from backend.creatoros.config import Settings
    import backend.creatoros.config as config
    import backend.creatoros.pipeline as pipeline
    import backend.creatoros.mesh as mesh
    import scripts.evaluate as evaluator

    settings = Settings(data_dir=tmp_path / "private", mesh_api_key="unit-test-not-a-key")
    monkeypatch.setattr(config, "load_settings", lambda: settings)
    initial_dir = tmp_path / "initial"
    assert asyncio.run(evaluate(argparse.Namespace(live=False, output=initial_dir, seed=2026))) == 0
    source_path = initial_dir / "results.json"
    source = json.loads(source_path.read_text())
    # A mocked live report tests judge recovery without any provider requests.
    source["mode"] = source["status"] = "live"
    source["config"].update(model=settings.chat_model, judge_prompt=evaluator.JUDGE_PROMPT,
                            opening_judge_prompt=evaluator.OPENING_PROMPT)
    scores = {name: 4 for name in evaluator.DIMENSIONS}
    saved_score = {"before": scores, "after": scores, "mean_before": 4, "mean_after": 4, "delta": 0}
    for case in source["cases"]:
        case["scores"] = copy.deepcopy(saved_score)
    source["cases"][0].update(scores=None, error="MeshError: mocked judge timeout", evaluation_stage="quality_judging")
    source["summary"] = summarize(source["cases"])
    source_path.write_text(json.dumps(source))
    judged = []

    async def fake_judge(client, brief, profile, before, after, rng):
        judged.append((brief, before, after))
        return copy.deepcopy(saved_score)

    async def reject_generation(*args, **kwargs):
        raise AssertionError("Completed generation must not be repeated for a judging failure")

    class NoNetworkClient:
        def __init__(self, settings):
            self.usage = []

    monkeypatch.setattr(mesh, "MeshClient", NoNetworkClient)
    monkeypatch.setattr(pipeline, "run_pipeline", reject_generation)
    monkeypatch.setattr(evaluator, "judge_pair", fake_judge)
    output = tmp_path / "recovered"
    assert asyncio.run(evaluate(argparse.Namespace(live=True, output=output, seed=2026, resume_results=source_path))) == 0
    result = json.loads((output / "results.json").read_text())
    assert len(judged) == 1
    assert result["cases"][1:] == source["cases"][1:]
    assert result["ablations"] == source["ablations"]
    assert result["cases"][0]["run"] == source["cases"][0]["run"]
    assert result["cases"][0]["before"] == source["cases"][0]["before"]
    assert result["cases"][0]["prior_attempts"] == [source["cases"][0]]
    assert result["summary"]["scored_pairs"] == 8

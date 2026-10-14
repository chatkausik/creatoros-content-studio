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
    assert result["config"]["brief_contracts_enforced"] is True
    assert all(case["scores"] is None for case in result["cases"])
    for pair in result["ablations"]:
        baseline, learned = pair["baseline_run"], pair["learned_run"]
        assert baseline["profile"] == learned["profile"]
        assert baseline["brief"] == learned["brief"]
        assert baseline["contract"] == learned["contract"]
        assert baseline["feedback_source"] == learned["feedback_source"] == "simulated"
        assert baseline["window"] == learned["window"] == "24h"
        assert baseline["use_learning"] is False
        assert learned["use_learning"] is True
        assert baseline["learning_snapshot_id"] is None
        assert learned["learning_snapshot_id"] is not None
        assert pair["baseline_hook"] == "problem-first"
        assert pair["learned_hook"] == "outcome-first"


def test_fresh_fixture_freezes_canonical_constraints_without_manufacturing_quality_scores(tmp_path, monkeypatch):
    from backend.creatoros.config import Settings
    from backend.creatoros.contracts import validate_contract
    import backend.creatoros.config as config
    from backend.creatoros.mesh import MeshClient
    import scripts.evaluate as evaluation

    monkeypatch.setattr(config, "load_settings", lambda: Settings(data_dir=tmp_path / "private", worker_enabled=False))
    # Exercise a constrained brief in both feedback branches, without changing
    # the repository's immutable benchmark manifest or historical reports.
    manifest = json.loads((evaluation.ROOT / "evals/cases.json").read_text())
    manifest["feedback_ablation_briefs"] = ["fresh-privacy"]
    manifest_root = tmp_path / "manifest"
    (manifest_root / "evals").mkdir(parents=True)
    (manifest_root / "evals/cases.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(evaluation, "ROOT", manifest_root)

    async def reject_ai(*args, **kwargs):
        raise AssertionError("Contract fixture evaluation must not call AI")

    monkeypatch.setattr(MeshClient, "complete_json", reject_ai)
    monkeypatch.setattr(MeshClient, "generate_image", reject_ai)
    output = tmp_path / "fresh-contracts"
    code = asyncio.run(evaluate(argparse.Namespace(live=False, output=output, seed=2026,
                                                  suite="fresh", case_limit=2)))
    result = json.loads((output / "results.json").read_text())
    assert code == 0
    assert result["config"]["brief_contracts_enforced"] is True
    assert result["summary"]["scored_pairs"] == 0
    assert result["summary"]["mean_before"] is result["summary"]["mean_after"] is None
    for case in result["cases"]:
        expected = validate_contract(case["constraints"], case["platform"])
        assert case["run"]["contract"] == case["post"]["contract"] == expected
        assert case["run"]["contract"]["max_words"] == 150
        assert case["scores"] is None
        assert case["before"] and case["after"]
        assert case["constraints_before"]["passed"] is not None
        assert case["constraints_after"]["passed"] is not None
        assert case["post"]["reviews"][0]["contract_checks"]
    ablation = result["ablations"][0]
    assert ablation["baseline_run"]["contract"] == ablation["learned_run"]["contract"] == result["cases"][0]["run"]["contract"]
    assert "not a guarantee that every final draft passes" in (output / "RESULTS.md").read_text()


def test_saved_report_without_enforcement_metadata_remains_explicitly_unknown(tmp_path, monkeypatch):
    from backend.creatoros.config import Settings
    import backend.creatoros.config as config
    from scripts.evaluate import write_results

    monkeypatch.setattr(config, "load_settings", lambda: Settings(data_dir=tmp_path / "private", worker_enabled=False))
    output = tmp_path / "report"
    asyncio.run(evaluate(argparse.Namespace(live=False, output=output, seed=2026,
                                          suite="fresh", case_limit=1, skip_ablations=True)))
    result = json.loads((output / "results.json").read_text())
    result["config"].pop("brief_contracts_enforced")
    original = copy.deepcopy(result)
    write_results(result, tmp_path / "historical-render")
    assert result == original
    restored = json.loads((tmp_path / "historical-render/results.json").read_text())
    assert "brief_contracts_enforced" not in restored["config"]
    assert "enforcement was not recorded" in (tmp_path / "historical-render/RESULTS.md").read_text()


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
                                     "clarity": value, "brand_fit": value, "factual_care": value, "rationale": "Evidence.", "opening_type": "unclear"}
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
    assert "factual_care" not in summary["by_dimension"]  # Old four-dimension evidence stays honest.
    assert summary["paired_change"]["small_n"] is True


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
    assert result["summary"]["first_pass_completed_pairs"] == 6
    assert result["summary"]["recovered_pairs"] == 2
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


def test_fresh_suite_is_distinct_bounded_and_covers_both_voices(tmp_path, monkeypatch):
    from scripts.evaluate import ROOT, select_cases
    from backend.creatoros.mesh import MeshClient

    manifest = json.loads((ROOT / "evals/cases.json").read_text())
    fresh = select_cases(manifest, "fresh")
    assert len(fresh) == 24
    assert {b["id"] for _, b in fresh}.isdisjoint({b["id"] for _, b in select_cases(manifest, "smoke")})
    assert len({p["brand_id"] for p, _ in select_cases(manifest, "fresh", 2)}) == 2
    assert all(b["constraints"]["max_words"] == 150 and "150" in b["brief"] for _, b in fresh)

    async def reject_ai(*args, **kwargs):
        raise AssertionError("Budget rejection and dry planning must make no AI call")

    monkeypatch.setattr(MeshClient, "complete_json", reject_ai)
    with pytest.raises(ValueError, match="exceeding"):
        asyncio.run(evaluate(argparse.Namespace(live=True, output=tmp_path, seed=2026, suite="fresh",
                                               max_generation_runs=1)))
    assert not (tmp_path / "results.json").exists()
    assert asyncio.run(evaluate(argparse.Namespace(live=True, output=tmp_path, seed=2026, suite="fresh",
                                                   plan_only=True))) == 0


def test_constraints_check_lengths_bullets_hashtags_and_markdown():
    from scripts.evaluation_metrics import constraint_checks
    checks = constraint_checks("**A title**\n- First item\n- Second item\n#AI", {
        "max_words": 5, "max_characters": 20, "min_bullets": 3, "max_hashtags": 0, "plain_text": True})
    assert checks["passed"] is False
    assert not any(checks["checks"].values())
    assert constraint_checks("A short line", {"min_words": 2, "max_words": 4})["passed"] is True
    assert constraint_checks("Unconstrained")['passed'] is None


def test_bootstrap_preserves_negative_differences_and_is_seeded():
    from scripts.evaluation_metrics import paired_bootstrap
    a = paired_bootstrap([-2, -1, 0, 1], seed=33)
    assert a == paired_bootstrap([-2, -1, 0, 1], seed=33)
    assert a["mean_delta"] == -0.5
    assert a["interval_95"][0] < 0 < a["interval_95"][1]
    assert paired_bootstrap([2, 2, 2])["interval_95"] == [2, 2]
    assert paired_bootstrap([])["interval_95"] is None


def test_learned_profiles_are_used_in_every_generation_and_voice_conditions(tmp_path, monkeypatch):
    import backend.creatoros.pipeline as pipeline
    import backend.creatoros.config as config
    from backend.creatoros.config import Settings
    from backend.creatoros.mesh import MeshClient

    monkeypatch.setattr(config, "load_settings", lambda: Settings(data_dir=tmp_path / "private"))
    extracted = []
    real_extract = pipeline.extract_profile

    async def learn(samples, settings, mode):
        result = await real_extract(samples, settings, mode)
        result["summary"] = f"Unique extracted profile {len(extracted)}"
        extracted.append(result)
        return result

    async def reject_ai(*args, **kwargs):
        raise AssertionError("Fixture learned-profile evaluation makes no paid request")

    monkeypatch.setattr(pipeline, "extract_profile", learn)
    monkeypatch.setattr(MeshClient, "complete_json", reject_ai)
    output = tmp_path / "report"
    code = asyncio.run(evaluate(argparse.Namespace(live=False, output=output, seed=2026,
                         suite="fresh", case_limit=2, learn_voices=True, voice_checks=True)))
    report = json.loads((output / "results.json").read_text())
    assert code == 0
    assert len(extracted) == 2
    assert [c["run"]["profile"] for c in report["cases"]] == extracted
    assert all(a["baseline_run"]["profile"] == a["learned_run"]["profile"] == extracted[0]
               for a in report["ablations"])
    records = report["voice_checks"]
    assert len(records) == 6 and not any(r.get("scored") for r in records)
    assert records[0]["run"]["profile"] == extracted[0]
    assert records[1]["run"]["profile"] == extracted[1]
    assert records[2]["run"]["profile"] not in extracted


def test_voice_classifier_is_blinded_and_recovers_anonymous_identity():
    from scripts.evaluation_voice import identify_voice

    class BlindJudge:
        async def complete_json(self, system, user, schema, **kwargs):
            payload = json.loads(user)
            assert set(payload) == {"candidate", "reference_a", "reference_b"}
            assert "target_brand_id" not in user and "condition" not in user and "profile" not in user
            key = next(k for k in ("reference_a", "reference_b") if payload[k]["samples"] == ["Direct sentences."])
            return schema.model_validate({"reference": key, "rationale": "Short direct wording."})

    brands = [{"id": "precise", "samples": [{"text": "Direct sentences."}]},
              {"id": "warm", "samples": [{"text": "Could we begin with a small question?"}]}]
    for seed in range(4):
        judged = asyncio.run(identify_voice(BlindJudge(), "Inspect the input.", brands, random.Random(seed)))
        assert judged["predicted_brand_id"] == "precise"


def test_recovery_rejects_judge_model_changes(tmp_path, monkeypatch):
    import backend.creatoros.config as config
    import scripts.evaluate as evaluator
    from backend.creatoros.config import Settings

    settings = Settings(data_dir=tmp_path / "private")
    monkeypatch.setattr(config, "load_settings", lambda: settings)
    output = tmp_path / "source"
    assert asyncio.run(evaluate(argparse.Namespace(live=False, output=output, seed=2026))) == 0
    source = json.loads((output / "results.json").read_text())
    source["mode"] = "live"
    source["config"].update(model=settings.chat_model, judge_model="other/model",
                             judge_prompt=evaluator.JUDGE_PROMPT, opening_judge_prompt=evaluator.OPENING_PROMPT)
    with pytest.raises(ValueError, match="changed judge_model"):
        evaluator.validate_recovery(source, settings, True, judge_model="changed/model")


def test_atomic_partial_checkpoint_retains_success_and_continues_remaining_cases(tmp_path, monkeypatch):
    import scripts.evaluate as evaluator
    import backend.creatoros.config as config
    from backend.creatoros.config import Settings

    monkeypatch.setattr(config, "load_settings", lambda: Settings(data_dir=tmp_path / "private"))
    real_checkpoint = evaluator.write_progress
    stopped = False

    def interrupt_after_first(result, output, rng, phase):
        nonlocal stopped
        real_checkpoint(result, output, rng, phase)
        if phase == "case-complete" and not stopped:
            stopped = True
            raise KeyboardInterrupt("Simulated process interruption")

    monkeypatch.setattr(evaluator, "write_progress", interrupt_after_first)
    output = tmp_path / "report"
    with pytest.raises(KeyboardInterrupt):
        asyncio.run(evaluate(argparse.Namespace(live=False, output=output, seed=2026,
                                               suite="fresh", case_limit=2, skip_ablations=True)))
    source = json.loads((output / "progress.json").read_text())
    assert source["status"] == "partial"
    assert source["progress"]["planned_pairs"] == 2
    assert source["progress"]["planned_completion_rate"] == 0.5
    assert len(source["progress"]["pending_pair_ids"]) == 1
    assert not (output / "results.json").exists()
    assert not list(output.glob(".progress-*"))
    monkeypatch.setattr(evaluator, "write_progress", real_checkpoint)
    assert asyncio.run(evaluate(argparse.Namespace(live=False, output=output, seed=2026,
                            resume_results=output / "progress.json"))) == 0
    final = json.loads((output / "results.json").read_text())
    assert final["cases"][0] == source["cases"][0]
    assert final["summary"]["completed_pairs"] == 2
    assert final["continuations"][0]["initial_progress"] == source["progress"]
    assert json.loads((output / "progress.json").read_text())["status"] == "fixture"


def test_partial_resume_reuses_completed_pipeline_after_interrupted_return(tmp_path, monkeypatch):
    import backend.creatoros.config as config
    import backend.creatoros.pipeline as pipeline
    from backend.creatoros.config import Settings

    monkeypatch.setattr(config, "load_settings", lambda: Settings(data_dir=tmp_path / "private"))
    original = pipeline.run_pipeline
    completed_ids = []

    async def interrupt_return(run_id, store, settings):
        await original(run_id, store, settings)
        completed_ids.append(run_id)
        raise asyncio.CancelledError("Interrupted between node persistence and report checkpoint")

    monkeypatch.setattr(pipeline, "run_pipeline", interrupt_return)
    output = tmp_path / "report"
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(evaluate(argparse.Namespace(live=False, output=output, seed=2026,
                           suite="fresh", case_limit=1, skip_ablations=True)))

    async def reject_reroll(*args, **kwargs):
        raise AssertionError("Persisted completed generation must not be rerun")

    monkeypatch.setattr(pipeline, "run_pipeline", reject_reroll)
    assert asyncio.run(evaluate(argparse.Namespace(live=False, output=output, seed=2026,
                           resume_results=output / "progress.json"))) == 0
    report = json.loads((output / "results.json").read_text())
    assert report["cases"][0]["run"]["id"] == completed_ids[0]
    assert report["summary"]["first_pass_completed_pairs"] == 0
    assert report["summary"]["recovered_pairs"] == 1
    assert report["cases"][0]["prior_attempts"][0]["error"].startswith("Evaluation process interrupted")


def test_transport_recovery_keeps_schema_failures_and_successes_unchanged(tmp_path, monkeypatch):
    import backend.creatoros.config as config
    import backend.creatoros.pipeline as pipeline
    from backend.creatoros.config import Settings
    from scripts.evaluate import transport_failure

    monkeypatch.setattr(config, "load_settings", lambda: Settings(data_dir=tmp_path / "private"))
    initial = tmp_path / "initial"
    assert asyncio.run(evaluate(argparse.Namespace(live=False, output=initial, seed=2026))) == 0
    path = initial / "results.json"
    report = json.loads(path.read_text())
    report["cases"][0]["error"] = "GenerationFailure: Mesh returned invalid structured output twice (SelectedStrategy)."
    report["cases"][1]["error"] = "MeshError: Mesh timed out. Your completed steps are saved; retry the failed step."
    report["summary"] = summarize(report["cases"])
    path.write_text(json.dumps(report))

    async def reject_generation(*args, **kwargs):
        raise AssertionError("Completed pipelines and schema failures must not be rerolled")

    monkeypatch.setattr(pipeline, "run_pipeline", reject_generation)
    output = tmp_path / "recovered"
    assert asyncio.run(evaluate(argparse.Namespace(live=False, output=output, seed=2026,
                        resume_results=path, retry_transport_only=True))) == 1
    recovered = json.loads((output / "results.json").read_text())
    assert recovered["cases"][0] == report["cases"][0]
    assert recovered["cases"][2:] == report["cases"][2:]
    assert recovered["cases"][1]["prior_attempts"] == [report["cases"][1]]
    assert recovered["recovery"]["attempts"][0]["retained_nontransport_failures"] == [report["cases"][0]["id"]]
    assert recovered["progress"]["phase"] == "complete"
    assert recovered["progress"]["completed_pairs"] == recovered["summary"]["completed_pairs"]
    assert recovered["progress"]["saved_at"] != report["progress"]["saved_at"]
    assert transport_failure({"error": "GenerationFailure: Could not connect to Mesh. Check your connection and retry."})
    assert not transport_failure({"error": "MeshError: Mesh credit or spend limit was reached."})

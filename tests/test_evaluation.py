"""Guard honest scoring and the controlled feedback comparison."""
import argparse
import asyncio
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

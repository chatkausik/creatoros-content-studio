"""Regression cases from an observed live run; no paid inference requests."""
import asyncio
import json

import pytest
from pydantic import ValidationError

from backend.creatoros.config import Settings
from backend.creatoros.fixtures import seed_demo
from backend.creatoros.mesh import MeshClient
from backend.creatoros.pipeline import run_pipeline
from backend.creatoros.schemas import Draft, InitialReview
from backend.creatoros.service import create_run
from backend.creatoros.store import Store


def review(scores=None, requests=None, approved=True):
    names = ("brief_fulfillment", "specificity", "clarity", "brand_fit", "factual_care")
    return {
        "criteria": [{"name": name, "score": (scores or {}).get(name, 4), "reason": "The current text addresses this criterion clearly."} for name in names],
        "requests": requests or [],
        "approved": approved,
    }


@pytest.mark.parametrize("markup", ["**A bold heading**", "## A heading", "`inline code`", "[A labeled link](https://example.com)"])
def test_linkedin_content_rejects_markdown(markup):
    content = f"{markup}\n\nSave a failing input before changing your evaluation. Rerun that exact input after one change. Keep both responses in the review."
    with pytest.raises(ValidationError):
        Draft.model_validate({"title": "A useful test", "content": content})


def test_linkedin_content_accepts_plain_text_bullets_and_emojis():
    content = "A polished demo can hide a failing case.\n\n→ Save the failing input.\n→ Change one instruction.\n→ Rerun the same case.\n\nWhat would you test first? 🔍"
    assert Draft.model_validate({"title": "A useful test", "content": content}).content == content


@pytest.mark.parametrize("hook", ["problem-first", "outcome-first"])
def test_statement_hooks_reject_observed_question_opening(hook):
    from backend.creatoros.pipeline import _validate_hook_opening

    with pytest.raises(ValueError, match="statement, not a question"):
        _validate_hook_opening("Are you maximizing the potential of your AI models?\n\nKeep a test you can inspect.", hook)


def test_statement_hook_can_include_a_later_question():
    from backend.creatoros.pipeline import _validate_hook_opening

    _validate_hook_opening("A polished demo can hide failures. Which one would you inspect?", "problem-first")
    _validate_hook_opening("Make your next change easier to inspect. Which test will you run?", "outcome-first")
    _validate_hook_opening("Which test will you run? Save its result.", "question-first")
    with pytest.raises(ValueError, match="first visible content sentence"):
        _validate_hook_opening("A polished demo can hide failures. Which one would you inspect?", "question-first")


@pytest.mark.parametrize("instruction", ['a document labeled "Failure"', "a screen labelled Rerun Cases", 'the words reading "Evaluation Loop"'])
def test_visual_brief_rejects_literal_labels(instruction):
    from backend.creatoros.schemas import VisualBrief

    with pytest.raises(ValidationError, match="no readable text"):
        VisualBrief.model_validate({"image_prompt": f"Create an editorial illustration of {instruction}, with soft green colors and a clean square composition.", "reason": "The visual communicates an evaluation loop."})


def test_visual_brief_allows_explicit_no_text_constraint():
    from backend.creatoros.schemas import VisualBrief

    prompt = "An editorial illustration of a blank page and a green loop, with no text, no labels, no letters, and no numbers."
    assert VisualBrief.model_validate({"image_prompt": prompt, "reason": "The visual communicates a feedback loop."}).image_prompt == prompt


def test_visual_generation_appends_trusted_constraint_after_model_prompt(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock
    from backend.creatoros.pipeline import generate_visual
    from backend.creatoros.prompts import VISUAL_CONSTRAINT
    from backend.creatoros.schemas import VisualBrief

    prompt = "An editorial illustration of a blank page and a green loop, with soft light and a clean square composition."
    monkeypatch.setattr(MeshClient, "complete_json", AsyncMock(return_value=VisualBrief(image_prompt=prompt, reason="The image represents an evaluation loop.")))
    image_call = AsyncMock(return_value={"image_url": "/assets/mock.png", "source": "mesh", "model": "mock-image"})
    monkeypatch.setattr(MeshClient, "generate_image", image_call)
    asyncio.run(generate_visual({"title": "A repeatable evaluation", "content": "Save a test and inspect the change."}, Settings(data_dir=tmp_path, mesh_api_key="mock-key"), "live"))
    assert image_call.await_args.args[0] == prompt + "\n\n" + VISUAL_CONSTRAINT


def test_initial_editor_still_requires_a_meaningful_revision_request():
    with pytest.raises(ValidationError):
        InitialReview.model_validate(review())


def test_refinement_retains_inconsistent_polish_request_for_human_review():
    from backend.creatoros import schemas
    from backend.creatoros.pipeline import _review_outcome

    original = review(requests=[{"issue": "More detail could help", "instruction": "Expand the already-present example with more detail."}], approved=False)
    validated = schemas.RefinementReview.model_validate(original)
    outcome = _review_outcome(validated.model_dump(), 1)
    assert outcome["raw_model_review"] == original
    assert outcome["requests"] == original["requests"]
    assert outcome["requires_human_review"]
    assert not outcome["approved"]


def test_refinement_missing_request_for_a_failing_criterion_needs_human_review():
    from backend.creatoros import schemas
    from backend.creatoros.pipeline import _review_outcome

    original = review(scores={"brief_fulfillment": 2}, approved=False)
    validated = schemas.RefinementReview.model_validate(original)
    outcome = _review_outcome(validated.model_dump(), 1)
    assert outcome["raw_model_review"] == original
    assert outcome["requires_human_review"]
    assert not outcome["approved"]


def test_refinement_still_rejects_duplicate_rubric_criteria():
    from backend.creatoros import schemas

    invalid = review()
    invalid["criteria"][1]["name"] = invalid["criteria"][0]["name"]
    with pytest.raises(ValidationError):
        schemas.RefinementReview.model_validate(invalid)


def test_refinement_accepts_rich_audit_reason_without_weakening_scores():
    from backend.creatoros.schemas import RefinementReview
    from backend.creatoros.pipeline import _review_outcome

    raw = review()
    reason = "The opening names a concrete problem, and the saved failure becomes a repeatable test. " * 7
    assert 500 < len(reason) < 1200
    raw["criteria"][0]["reason"] = reason.strip()
    validated = RefinementReview.model_validate(raw)
    outcome = _review_outcome(validated.model_dump(), 1)
    assert outcome["approved"]
    assert outcome["criteria"][0]["reason"] == reason.strip()
    raw["criteria"][0]["reason"] = "x" * 1201
    with pytest.raises(ValidationError):
        RefinementReview.model_validate(raw)


@pytest.mark.parametrize("inconsistent", [False, True])
def test_editor_can_correct_opening_against_the_frozen_hook_policy(tmp_path, monkeypatch, inconsistent):
    settings = Settings(data_dir=tmp_path, mesh_api_key="mock-key")
    store = Store(tmp_path)
    seed_demo(store)
    run = create_run(store, settings, {"brand_id": "brand-milo", "brief": "Explain a practical evaluation feedback loop.", "mode": "live", "use_learning": False})
    assert run["selected_hook"] == "problem-first"
    original = "Transform failures into learning opportunities.\n\nSave the input, change one thing and rerun the same cases. Testing can become a regular habit for your team. What will you improve next?"
    revised = "A polished demo can hide the failure your users encounter.\n\nTry a small rehearsal. Save one ambiguous request and the response it produced. Change a single instruction, then rerun that exact request. Compare both responses before widening the test.\n\nWhich difficult input would you bring to that rehearsal?"
    request = {"issue": "The opening promises an outcome instead of naming a problem.", "instruction": "Replace the first sentence with a concrete failure or risk, then retain the practical feedback-loop steps."}
    final_review = review(requests=[{"issue": "The opening could be more engaging.", "instruction": "Consider making the already-revised opening more compelling."}], approved=False) if inconsistent else review()
    answers = [
        {"angle": "Use a small rehearsal to expose evaluation failures", "hook": "problem-first", "audience": "AI builders", "outline": ["Name the failure", "Describe a small test", "Invite a concrete case"], "reason": "Initial exploration follows the selected problem-first policy."},
        {"title": "An evaluation rehearsal", "content": original},
        review(scores={"brief_fulfillment": 3}, requests=[request], approved=False),
        {"title": "An evaluation rehearsal", "content": revised, "addressed_requests": ["Replaced the outcome headline with a concrete demo failure, then preserved the test steps."]},
        final_review,
    ]
    editor_inputs = []

    async def respond(_client, endpoint, payload, timeout=None, cache=True):
        if "Your role is EDITOR" in payload["messages"][0]["content"]:
            editor_inputs.append(json.loads(payload["messages"][1]["content"]))
        return {"choices": [{"message": {"content": json.dumps(answers.pop(0))}}]}

    monkeypatch.setattr(MeshClient, "_post", respond)
    asyncio.run(run_pipeline(run["id"], store, settings))
    post = store.get("posts", run["post_id"])
    assert store.get("runs", run["id"])["status"] == "complete"
    assert post["content"].splitlines()[0] == revised.splitlines()[0]
    assert post["original_draft"] == original
    assert all(item["selected_hook"] == "problem-first" for item in editor_inputs)
    assert editor_inputs[1]["previous_requests"] == [request]
    assert editor_inputs[1]["previous_draft"]["content"] == original
    assert editor_inputs[1]["addressed_requests"] == post["versions"][1]["addressed_requests"]
    assert post["reviews"][0]["requests"] == [request]
    assert post["status"] == ("needs_review" if inconsistent else "draft")
    assert len(post["versions"]) == 2
    assert len(post["reviews"]) == 2
    assert not answers
    if inconsistent:
        assert post["reviews"][-1]["raw_model_review"] == final_review
        assert post["reviews"][-1]["requests"] == final_review["requests"]
        assert any(event["choice"] == "Editor judgment requires human review" for event in store.list("events", post_id=post["id"]))

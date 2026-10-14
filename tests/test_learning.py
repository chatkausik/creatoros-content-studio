from copy import deepcopy

from backend.creatoros.learning import HOOKS, build_snapshot, select_hook


def post(identifier, hook="problem-first", brand="a", **changes):
    return {"id": identifier, "brand_id": brand, "hook": hook,
            "status": "published_manually", "is_demo": False, **changes}


def observation(identifier, post_id, **changes):
    return {"id": identifier, "post_id": post_id, "source": "manual", "window": "24h",
            "impressions": 1000, "comments": 10, "reposts": 2, **changes}


def test_feedback_scopes_and_missing_impressions_cannot_change_policy():
    posts = [post("included"), post("other-brand", brand="b"), post("demo", is_demo=True),
             post("draft", status="draft"), post("zero"), post("missing")]
    missing = observation("missing-count", "missing")
    missing.pop("impressions")
    feedback = [observation("valid", "included"), observation("alien", "other-brand", comments=999),
                observation("simulation", "included", source="simulated", comments=999),
                observation("week", "included", window="7d", comments=999),
                observation("demo-manual", "demo", comments=999),
                observation("unpublished", "draft", comments=999),
                observation("zero-count", "zero", impressions=0, comments=999), missing]
    snapshot = build_snapshot(posts, feedback, "a", "manual", "24h", 1)
    assert snapshot["evidence_ids"] == ["valid"]
    assert snapshot["stats"][0]["rate"] == 12
    assert snapshot["stats"][0]["posts"] == 1
    assert snapshot["preferred_hook"] is None
    assert [select_hook(snapshot, i)[0] for i in range(6)] == list(HOOKS) * 2


def test_counts_are_pooled_and_duplicate_observations_do_not_inflate_them():
    posts = [post("small"), post("large")]
    feedback = [observation("outdated", "small", impressions=100, comments=100, reposts=0),
                observation("replacement", "small", impressions=100, comments=10, reposts=0),
                observation("large", "large", impressions=900, comments=9, reposts=0)]
    snapshot = build_snapshot(posts, feedback, "a", "manual", "24h", 1)
    stat = snapshot["stats"][0]
    assert stat["posts"] == 2
    assert stat["impressions"] == 1000
    assert stat["rate"] == 19  # Counts pooled; an unweighted rate average would be 55.
    assert snapshot["evidence_ids"] == ["large", "replacement"]


def test_reversal_changes_preference_and_every_fourth_selection_explores():
    posts = [post(f"p{i}", hook=hook) for i, hook in enumerate(HOOKS)]
    feedback = [observation(f"f{i}", p["id"], comments=count, reposts=0)
                for i, (p, count) in enumerate(zip(posts, (5, 40, 10)))]
    original = deepcopy(feedback)
    first = build_snapshot(posts, feedback, "a", "manual", "24h", 1)
    feedback[0]["comments"], feedback[1]["comments"] = 50, 4
    second = build_snapshot(posts, feedback, "a", "manual", "24h", 2)
    assert first["preferred_hook"] == "outcome-first"
    assert second["preferred_hook"] == "problem-first"
    assert first["stats"][0]["comments"] == original[0]["comments"]
    selections = [select_hook(first, i)[0] for i in range(12)]
    assert all(hook == "outcome-first" for i, hook in enumerate(selections) if (i + 1) % 4)
    assert [selections[i] for i in (3, 7, 11)] == ["problem-first", "question-first", "problem-first"]


def test_ties_rotate_without_being_mislabeled_as_zero_data():
    posts = [post(f"p{i}", hook=hook) for i, hook in enumerate(HOOKS)]
    feedback = [observation(f"f{i}", p["id"], comments=0, reposts=0) for i, p in enumerate(posts)]
    snapshot = build_snapshot(posts, feedback, "a", "manual", "24h", 1)
    assert snapshot["status"] == "early_signal"
    assert all(stat["rate"] == 0 for stat in snapshot["stats"])
    assert [select_hook(snapshot, i)[0] for i in range(3)] == list(HOOKS)

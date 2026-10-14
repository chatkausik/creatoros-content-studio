import csv
import io
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.creatoros.config import Settings
from backend.creatoros.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path, worker_enabled=False))) as client:
        stamp = datetime.now(timezone.utc) - timedelta(days=3)
        store = client.app.state.store
        for number in (1, 2):
            store.put("posts", {"id": f"import-post-{number}", "brand_id": "brand-ada", "title": f"Published example {number}",
                "platform": "linkedin", "published_at": stamp.isoformat(), "created_at": stamp.isoformat(),
                "content": "A published post with a problem-first opening.", "hook": "problem-first",
                "status": "published_manually", "is_demo": False, "source_url": f"https://example.com/posts/{number}"})
        yield client


def row(client, **changes):
    post = client.app.state.store.get("posts", "import-post-1")
    value = {"post_id": post["id"], "source_url": post["source_url"], "published_at": post["published_at"],
             "observed_at": (datetime.fromisoformat(post["published_at"]) + timedelta(hours=24)).isoformat(),
             "window": "24h", "impressions": "1000", "comments": "7", "reposts": "2", "notes": "Creator export"}
    value.update(changes)
    return value


def csv_text(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def preview(client, rows, **kwargs):
    return client.post("/api/feedback-imports/preview", json={"brand_id": "brand-ada", "platform": "linkedin",
                        "source": "manual", "csv_text": csv_text(rows), **kwargs})


def commit(client, result):
    return client.post(f"/api/feedback-imports/{result['id']}/commit", json={})


def test_preview_commit_reimport_and_correction_preserve_history(client):
    store = client.app.state.store
    first = preview(client, [row(client)]).json()
    assert first["rows"][0]["status"] == "new" and first["rows"][0]["eligible"]
    assert store.get("feedback", "import-post-1:manual:24h") is None
    saved = commit(client, first).json()
    assert saved["saved"] == 1 and saved["committed"]
    initial = store.get("feedback", "import-post-1:manual:24h")
    assert commit(client, first).json() == saved
    repeat = preview(client, [row(client)]).json()
    assert repeat["rows"][0]["status"] == "unchanged"
    assert commit(client, repeat).json()["unchanged"] == 1
    corrected = preview(client, [row(client, comments="9")]).json()
    assert corrected["rows"][0]["status"] == "update"
    assert commit(client, corrected).json()["updated"] == 1
    current = store.get("feedback", "import-post-1:manual:24h")
    assert current["revision"] == 2 and current["comments"] == 9
    assert store.get("feedback_revisions", initial["revision_id"])["comments"] == 7
    assert len(store.list("feedback", post_id="import-post-1")) == 1


def test_csv_and_manual_endpoint_share_idempotency(client):
    result = preview(client, [row(client)]).json()
    commit(client, result)
    existing = client.app.state.store.get("feedback", "import-post-1:manual:24h")
    response = client.put("/api/posts/import-post-1/feedback", json=result["rows"][0]["payload"])
    assert response.status_code == 200 and response.json()["revision_id"] == existing["revision_id"]


@pytest.mark.parametrize("changes", [{"window": "cumulative"}, {"window": "unknown"}, {"impressions": "0"}, {"observed_at": ""},
    {"observed_at": "2020-01-01T00:00:00Z"}])
def test_noncomparable_observations_are_retained_but_excluded(client, changes):
    result = preview(client, [row(client, **changes)]).json()
    assert result["rows"][0]["status"] == "new"
    assert result["rows"][0]["eligible"] is False and result["rows"][0]["exclusion_reason"]
    assert commit(client, result).status_code == 200
    snapshot = client.post("/api/brands/brand-ada/learn", json={"source": "manual", "window": "24h"}).json()
    assert not snapshot["evidence"]


@pytest.mark.parametrize("changes", [{"impressions": "-3"}, {"comments": "1.2"}, {"observed_at": "2020-01-01"},
    {"source_url": "javascript:alert(1)"}, {"source_url": "https://example.com/wrong"},
    {"published_at": "2020-01-01T00:00:00Z"}, {"post_id": "not-this-brand"}])
def test_bad_rows_are_explained_and_not_saved(client, changes):
    result = preview(client, [row(client, **changes)]).json()
    assert result["rows"][0]["status"] == "invalid" and result["rows"][0]["errors"]
    assert commit(client, result).status_code == 422


def test_duplicate_and_conflicting_rows_are_never_counted_twice(client):
    same = row(client)
    result = preview(client, [same, same]).json()
    assert [r["status"] for r in result["rows"]] == ["new", "duplicate"]
    assert commit(client, result).json()["saved"] == 1
    conflicting = preview(client, [row(client, comments="8"), row(client, comments="11")]).json()
    assert [r["status"] for r in conflicting["rows"]] == ["invalid", "invalid"]
    assert commit(client, conflicting).status_code == 422


def test_stale_preview_does_not_save_even_earlier_valid_rows(client):
    first, second = row(client), row(client, post_id="import-post-2", source_url="https://example.com/posts/2")
    result = preview(client, [first, second]).json()
    store = client.app.state.store
    store.patch("posts", "import-post-2", {"hook": "question-first"})
    assert commit(client, result).status_code == 409
    assert not store.get("feedback", "import-post-1:manual:24h")
    assert not store.get("feedback_imports", result["id"])["committed"]


def test_stale_feedback_correction_requires_fresh_preview(client):
    initial = preview(client, [row(client)]).json()
    commit(client, initial)
    candidate = preview(client, [row(client, comments="9")]).json()
    changed = {**initial["rows"][0]["payload"], "comments": 15}
    assert client.put("/api/posts/import-post-1/feedback", json=changed).status_code == 200
    assert commit(client, candidate).status_code == 409
    assert client.app.state.store.get("feedback", "import-post-1:manual:24h")["comments"] == 15


def test_column_mapping_and_url_only_match(client):
    source = row(client)
    custom = {"Post link": source["source_url"] + "/", "Views": "1000", "Measured": source["observed_at"], "Period": "24h"}
    result = preview(client, [custom], mapping={"source_url": "Post link", "impressions": "Views", "observed_at": "Measured", "window": "Period"}).json()
    assert result["rows"][0]["post_id"] == "import-post-1" and result["rows"][0]["eligible"]


def test_demo_posts_cannot_be_mislabeled_as_real_metrics(client):
    client.app.state.store.patch("posts", "import-post-1", {"is_demo": True})
    assert preview(client, [row(client)]).json()["rows"][0]["status"] == "invalid"
    result = preview(client, [row(client)], source="simulated").json()
    assert result["rows"][0]["status"] == "new"


def test_draft_with_publication_column_is_a_row_error_not_server_error(client):
    client.app.state.store.patch("posts", "import-post-1", {"status": "draft", "published_at": None})
    result = preview(client, [{"post_id": "import-post-1", "published_at": "2020-01-01T00:00:00Z", "impressions": "100"}])
    assert result.status_code == 200
    assert result.json()["rows"][0]["status"] == "invalid"
    assert "published" in result.json()["rows"][0]["errors"][0]


def test_ambiguous_url_and_cross_platform_matches_rejected(client):
    store = client.app.state.store
    store.patch("posts", "import-post-2", {"source_url": "https://example.com/posts/1"})
    assert preview(client, [row(client, post_id="")]).json()["rows"][0]["status"] == "invalid"
    assert preview(client, [row(client)], platform="newsletter").json()["rows"][0]["status"] == "invalid"


def test_bad_header_limits_and_atomic_storage(client):
    assert client.post("/api/feedback-imports/preview", json={"brand_id": "brand-ada", "csv_text": "post_id,post_id\na,a\n"}).status_code == 422
    assert preview(client, [row(client)] * 251).status_code == 422
    store = client.app.state.store
    with pytest.raises(Exception):
        store.put_many([("atomic_test", {"id": "first", "value": 1}), ("atomic_test", {"id": "bad", "value": object()})])
    assert store.get("atomic_test", "first") is None


def test_valid_rows_commit_while_invalid_rows_remain_visible(client):
    result = preview(client, [row(client), row(client, post_id="unknown")]).json()
    saved = commit(client, result).json()
    assert saved["saved"] == 1 and saved["skipped"] == 1
    assert saved["rows"][1]["errors"]

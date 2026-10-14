"""Preview CSV observations, then atomically commit exactly the reviewed changes."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

from .feedback import FeedbackInput, FeedbackError, eligibility, make_observation, prepare_feedback, unchanged
from .store import utcnow

COLUMNS = ["post_id", "source_url", "published_at", "observed_at", "window", "window_start", "window_end",
           "impressions", "reactions", "comments", "reposts", "notes"]
ALIASES = {"post_url": "source_url", "url": "source_url", "published_time": "published_at",
           "measurement_time": "observed_at", "measured_at": "observed_at", "shares": "reposts"}
TEMPLATE = ",".join(COLUMNS) + "\n"


class PreviewInput(BaseModel):
    brand_id: str
    platform: Literal["linkedin", "newsletter"] = "linkedin"
    source: Literal["manual", "simulated"] = "manual"
    csv_text: str = Field(min_length=1, max_length=1_000_000)
    mapping: dict[str, str] | None = None


def canonical_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("Use a full HTTP or HTTPS post URL.")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def post_basis(post: dict) -> dict:
    return {key: post.get(key) for key in ("id", "brand_id", "platform", "status", "published_at", "hook", "is_demo", "source_url")}


def preview_import(store, payload: PreviewInput) -> dict:
    if not store.get("brands", payload.brand_id):
        raise HTTPException(404, "Brand not found.")
    try:
        reader = csv.DictReader(io.StringIO(payload.csv_text.lstrip("\ufeff")), strict=True)
        columns = reader.fieldnames or []
        if not columns or len(columns) > 30 or len(set(columns)) != len(columns) or any(not c.strip() for c in columns):
            raise ValueError("Use a CSV header with unique, nonempty column names (maximum 30 columns).")
        rows = []
        for row in reader:
            if len(rows) >= 250:
                raise ValueError("Import at most 250 observations at a time.")
            rows.append(row)
    except (csv.Error, ValueError) as error:
        raise HTTPException(422, str(error)) from None
    if not rows:
        raise HTTPException(422, "Add at least one data row below the CSV header.")
    mapping = payload.mapping
    if mapping is None:
        mapping = {}
        for column in columns:
            normalized = re.sub(r"[\s-]+", "_", column.strip().lower())
            key = ALIASES.get(normalized, normalized)
            if key in COLUMNS:
                if key in mapping:
                    raise HTTPException(422, f"Multiple columns map to {key}; choose an explicit mapping.")
                mapping[key] = column
    mapping = {key: value for key, value in mapping.items() if value}
    if any(key not in COLUMNS or value not in columns for key, value in mapping.items()):
        raise HTTPException(422, "Map supported observation fields to columns present in this file.")
    if len(set(mapping.values())) != len(mapping):
        raise HTTPException(422, "Map each CSV column to only one observation field.")
    if "impressions" not in mapping or not ({"post_id", "source_url"} & mapping.keys()):
        raise HTTPException(422, "Map impressions and either post_id or source_url before previewing.")
    posts = store.list("posts", brand_id=payload.brand_id)
    posts = [p for p in posts if p.get("platform", "linkedin") == payload.platform]
    by_id = {p["id"]: p for p in posts}
    by_url = {}
    for post in posts:
        if post.get("source_url"):
            try:
                by_url.setdefault(canonical_url(post["source_url"]), []).append(post)
            except ValueError:
                pass
    output, seen = [], {}
    for number, row in enumerate(rows, 2):
        item = {"row_number": number, "status": "invalid", "eligible": False, "errors": [],
                "post_id": None, "post_title": None}
        output.append(item)
        try:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Row length does not match the CSV header; quote fields containing commas.")
            values = {key: row[column].strip() for key, column in mapping.items()}
            identifier, source_url = values.get("post_id"), values.get("source_url", "")
            normalized_url = canonical_url(source_url) if source_url else None
            post = by_id.get(identifier) if identifier else None
            if identifier and not post:
                raise ValueError("Post ID does not belong to the selected brand and platform.")
            if not post and normalized_url:
                matches = by_url.get(normalized_url, [])
                if len(matches) != 1:
                    raise ValueError("Post URL must match exactly one existing post; supply its post_id to disambiguate.")
                post = matches[0]
            if not post:
                raise ValueError("Provide a published post ID or a matching imported post URL.")
            if normalized_url and post.get("source_url") and canonical_url(post["source_url"]) != normalized_url:
                raise ValueError("The post ID and URL point to different source records.")
            item.update(post_id=post["id"], post_title=post.get("title", ""))
            if post.get("status") not in {"published", "published_manually"} or not post.get("published_at"):
                raise ValueError("Only published posts with a saved publication time can receive performance feedback.")
            if values.get("published_at"):
                published = datetime.fromisoformat(values["published_at"].replace("Z", "+00:00"))
                actual = datetime.fromisoformat(post["published_at"].replace("Z", "+00:00"))
                if published.tzinfo is None or abs(published - actual) > timedelta(minutes=1):
                    raise ValueError("Published time must include a timezone and match the saved post within one minute.")
            data = {"source": payload.source, "window": values.get("window") or "unknown",
                    "source_url": source_url, "notes": values.get("notes", "")}
            for key in ("impressions", "reactions", "comments", "reposts"):
                raw = values.get(key, "")
                if not raw and key != "impressions":
                    data[key] = 0
                elif re.fullmatch(r"\d{1,13}", raw):
                    data[key] = int(raw)
                else:
                    raise ValueError(f"{key} must be a nonnegative whole number without separators.")
            for key in ("observed_at", "window_start", "window_end"):
                if values.get(key):
                    data[key] = values[key]
            feedback = FeedbackInput.model_validate(data)
            observation = make_observation(post, feedback)
            previous = store.get("feedback", observation["id"])
            eligible, reason = eligibility(observation, post)
            item.update(status="unchanged" if unchanged(previous, observation) else "update" if previous else "new",
                        eligible=eligible, exclusion_reason=reason, observation=observation,
                        payload=feedback.model_dump(mode="json"),
                        baseline={"post": fingerprint(post_basis(post)), "feedback": fingerprint(previous)})
            prior = seen.get(observation["id"])
            if prior:
                if prior.get("payload") == item["payload"]:
                    item.update(status="duplicate", eligible=False, errors=[f"Duplicate of row {prior['row_number']}; it will be skipped."])
                else:
                    message = "Conflicting rows for the same post/source/window; resolve them before importing these observations."
                    prior.update(status="invalid", eligible=False, errors=[message])
                    item.update(status="invalid", eligible=False, errors=[message])
            else:
                seen[observation["id"]] = item
        except ValidationError as error:
            item["errors"] = [e["msg"] for e in error.errors(include_input=False)]
        except (ValueError, TypeError, KeyError, FeedbackError) as error:
            item["errors"] = [str(error)]
    counts = Counter(item["status"] for item in output)
    valid = [item for item in output if item["status"] in {"new", "update", "unchanged"}]
    preview = {"id": str(uuid4()), "brand_id": payload.brand_id, "platform": payload.platform,
               "source": payload.source, "columns": columns, "mapping": mapping, "rows": output,
               "summary": {**{key: counts[key] for key in ("new", "update", "unchanged", "invalid", "duplicate")},
                           "eligible": sum(item["eligible"] for item in valid),
                           "excluded": sum(not item["eligible"] for item in valid)},
               "created_at": utcnow(), "committed": False,
               "file_sha256": hashlib.sha256(payload.csv_text.encode()).hexdigest()}
    store.put("feedback_imports", preview)
    return preview


def commit_import(store, identifier: str) -> dict:
    with store.lock:
        preview = store.get("feedback_imports", identifier)
        if not preview:
            raise HTTPException(404, "Import preview not found.")
        if preview.get("committed"):
            return preview
        valid = [item for item in preview["rows"] if item["status"] in {"new", "update", "unchanged"}]
        if not valid:
            raise HTTPException(422, "There are no valid observations to import. Correct the file and preview again.")
        records = []
        for item in valid:
            post = store.get("posts", item["post_id"])
            previous = store.get("feedback", item["observation"]["id"])
            if not post or fingerprint(post_basis(post)) != item["baseline"]["post"] or fingerprint(previous) != item["baseline"]["feedback"]:
                raise HTTPException(409, "A post or observation changed since preview. Preview the file again before importing; nothing was saved.")
            observation, writes = prepare_feedback(store, post, FeedbackInput.model_validate(item["payload"]))
            item["observation"] = observation
            records.extend(writes)
        preview.update(committed=True, committed_at=utcnow(), saved=preview["summary"]["new"],
                       updated=preview["summary"]["update"], unchanged=preview["summary"]["unchanged"],
                       skipped=preview["summary"]["invalid"] + preview["summary"]["duplicate"])
        records.append(("feedback_imports", preview))
        store.put_many(records)
        return preview


router = APIRouter(prefix="/api/feedback-imports", tags=["Feedback imports"])


@router.get("/template")
def template():
    return {"csv_text": TEMPLATE, "columns": COLUMNS}


@router.post("/preview")
def preview(payload: PreviewInput, request: Request):
    with request.app.state.store.lock:
        return preview_import(request.app.state.store, payload)


@router.post("/{identifier}/commit")
def commit(identifier: str, request: Request):
    return commit_import(request.app.state.store, identifier)

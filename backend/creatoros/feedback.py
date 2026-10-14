"""Shared feedback validation and atomic revision planning for manual and CSV input."""
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4
from pydantic import BaseModel, Field, field_validator, model_validator
from .store import utcnow

Source = Literal["manual", "simulated"]


class FeedbackInput(BaseModel):
    impressions: int = Field(ge=0, le=10**12, strict=True)
    reactions: int = Field(default=0, ge=0, le=10**12, strict=True)
    comments: int = Field(default=0, ge=0, le=10**12, strict=True)
    reposts: int = Field(default=0, ge=0, le=10**12, strict=True)
    window: Literal["24h", "7d", "unknown", "cumulative"] = "24h"
    source: Source = "manual"
    observed_at: datetime | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    source_url: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=1200)

    @field_validator("observed_at", "window_start", "window_end")
    @classmethod
    def valid_observation_time(cls, value):
        if value is not None:
            if value.tzinfo is None or value > datetime.now(timezone.utc):
                raise ValueError("Measurement time must include a timezone and cannot be in the future.")
            return value.astimezone(timezone.utc)
        return value


    @model_validator(mode="after")
    def complete_interval(self):
        if bool(self.window_start) != bool(self.window_end):
            raise ValueError("Provide both the measurement window start and end, or leave both empty.")
        if self.window_start and self.window_end <= self.window_start:
            raise ValueError("The measurement window must end after it starts.")
        return self

    @field_validator("source_url")
    @classmethod
    def safe_source_url(cls, value):
        if value and (urlparse(value).scheme not in {"https", "http"} or not urlparse(value).netloc):
            raise ValueError("Use a full HTTP or HTTPS source URL.")
        return value

class FeedbackError(ValueError):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


def make_observation(post: dict, payload: FeedbackInput) -> dict:
    if post["status"] not in {"published_manually", "published"}:
        raise FeedbackError("Only published posts can receive performance feedback.")
    if post.get("is_demo") and payload.source != "simulated":
        raise FeedbackError("Demonstration posts can only receive simulated feedback.", 400)
    duration = {"24h": timedelta(hours=24), "7d": timedelta(days=7)}.get(payload.window)
    published = datetime.fromisoformat(post["published_at"].replace("Z", "+00:00"))
    expected = published + duration if duration else None
    timing = "simulated" if payload.source == "simulated" else "unverified"
    if payload.source != "simulated" and payload.observed_at and expected:
        tolerance = timedelta(hours=1 if payload.window == "24h" else 6)
        if payload.window_start and payload.window_end:
            matched = (abs(payload.window_start - published) <= timedelta(minutes=1)
                       and abs(payload.window_end - expected) <= timedelta(minutes=1)
                       and payload.observed_at >= payload.window_end)
        else:
            matched = abs(payload.observed_at - expected) <= tolerance
        timing = "window_matched" if matched else "out_of_window"
    return {**payload.model_dump(mode="json"), "id": f"{post['id']}:{payload.source}:{payload.window}",
            "post_id": post["id"], "brand_id": post["brand_id"], "platform": post.get("platform", "linkedin"),
            "captured_at": utcnow(), "timing_status": timing,
            "window_start": payload.window_start.isoformat() if payload.window_start else published.isoformat() if duration else None,
            "window_end": payload.window_end.isoformat() if payload.window_end else expected.isoformat() if expected else None,
            "window_basis": "declared_interval" if payload.window_start else "capture_age" if payload.observed_at else "unverified"}


def unchanged(previous: dict | None, observation: dict) -> bool:
    return bool(previous and all(previous.get(key) == value for key, value in observation.items()
                                 if key not in {"captured_at", "revision_id", "revision"}))


def eligibility(observation: dict, post: dict) -> tuple[bool, str | None]:
    from .learning import HOOKS
    if post.get("hook") not in HOOKS:
        return False, "The published post needs a recognized opening classification."
    if observation["window"] not in {"24h", "7d"}:
        return False, "Unknown or cumulative windows are retained but excluded from learning."
    if observation["impressions"] <= 0:
        return False, "Zero impressions cannot establish an engagement rate."
    if observation["source"] != "simulated" and observation["timing_status"] != "window_matched":
        return False, "Measurement time does not establish a comparable observation window."
    return True, None


def prepare_feedback(store, post: dict, payload: FeedbackInput) -> tuple[dict, list[tuple[str, dict]]]:
    """Plan all writes; caller holds store.lock and commits with put_many."""
    observation = make_observation(post, payload)
    previous = store.get("feedback", observation["id"])
    if unchanged(previous, observation):
        return previous, []
    records = []
    if previous and not previous.get("revision_id"):
        records.append(("feedback_revisions", {**previous, "id": str(uuid4()),
                                               "feedback_id": previous["id"], "legacy": True}))
    revision_id = str(uuid4())
    observation.update(revision_id=revision_id, revision=(previous or {}).get("revision", 0) + 1)
    records.extend([
        ("feedback_revisions", {**observation, "id": revision_id, "feedback_id": observation["id"]}),
        ("feedback", observation),
        ("events", {"id": str(uuid4()), "post_id": post["id"], "node": "feedback",
                    "choice": f"Recorded {payload.window} performance",
                    "reason": f"{payload.source} observation: {payload.impressions} impressions, {payload.comments} comments, {payload.reposts} reposts. Timing: {observation['timing_status']}.",
                    "evidence_ids": [revision_id], "created_at": utcnow()}),
    ])
    return observation, records

"""Preregistered opening experiments with fixed assignments and frozen analyses.

Assignment is randomized before outcomes. Results remain descriptive: topic,
publishing time, audience, missing outcomes and manual editing can confound them.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime
import hashlib
import json
import random
import secrets
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .learning import HOOKS, MIN_IMPRESSIONS, MIN_POSTS, build_snapshot, select_hook
from .store import utcnow

METRIC = "comments + reposts per 1,000 impressions"
LIMITATIONS = [
    "Assignments are fixed before generation; every assigned slot remains visible, including failures and missing observations.",
    "Only the registered platform, provenance and measurement window are compared. Demo metrics are simulated, not audience evidence.",
    "Random assignment alone does not control topic, publishing time, audience, edits or missing outcomes. These results do not establish causal uplift or statistical significance.",
    "Repeated analyses are descriptive snapshots, not independent tests. A complete cohort with at least three posts and 300 impressions per opening is required before reporting a descriptive preference.",
]
STATUSES = ("pending", "queued", "running", "failed", "interrupted", "awaiting_publish",
            "awaiting_observation", "excluded", "eligible")


class ExperimentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brand_id: str
    name: str = Field(min_length=3, max_length=120)
    hypothesis: str = Field(min_length=10, max_length=1200)
    platform: Literal["linkedin", "newsletter"] = "linkedin"
    source: Literal["manual", "simulated"] = "simulated"
    window: Literal["24h", "7d"] = "24h"
    slots_per_hook: int = Field(default=3, ge=1, le=10, strict=True)

    @field_validator("name", "hypothesis")
    @classmethod
    def meaningful_text(cls, value, info):
        if len(value.strip()) < (3 if info.field_name == "name" else 10):
            raise ValueError("Provide meaningful text, not only whitespace.")
        return value.strip()


class SlotRunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brief: str = Field(min_length=10, max_length=6000)
    mode: Literal["demo", "live"] = "demo"
    generate_image: bool = False
    model_preset: Literal["budget", "submission-tested"] | None = None
    contract: dict | None = None


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _plan_hash(experiment):
    fixed = {key: experiment[key] for key in (
        "id", "brand_id", "name", "hypothesis", "platform", "source", "window",
        "slots_per_hook", "metric", "registered_at", "profile", "profile_version",
        "baseline_snapshot", "randomization_seed", "randomization_method",
    )}
    fixed["slots"] = [{key: slot[key] for key in ("id", "ordinal", "hook")} for slot in experiment["slots"]]
    return hashlib.sha256(_canonical(fixed).encode()).hexdigest()


def _required(store, identifier):
    experiment = store.get("experiments", identifier)
    if experiment is None:
        raise KeyError("Experiment not found.")
    if experiment["preregistration_hash"] != _plan_hash(experiment):
        raise ValueError("The frozen experiment registration has changed. Restore its original data before continuing.")
    if experiment.get("comparison") and experiment["comparison"].get("registration_hash") != _comparison_hash(experiment["comparison"]):
        raise ValueError("The frozen paired comparison has changed. Restore its original data before continuing.")
    return experiment


def _comparison_hash(comparison):
    fixed = {key: value for key, value in comparison.items() if key not in {"branches", "registration_hash"}}
    fixed["branches"] = [{key: branch[key] for key in ("id", "ordinal", "condition", "hook", "reason")}
                         for branch in comparison["branches"]]
    return hashlib.sha256(_canonical(fixed).encode()).hexdigest()


def _find_slot(experiment, slot_id):
    for slot in experiment["slots"]:
        if slot["id"] == slot_id:
            return slot, None
    comparison = experiment.get("comparison")
    if comparison:
        for branch in comparison["branches"]:
            if branch["id"] == slot_id:
                return branch, comparison
    raise KeyError("Experiment slot not found.")


def create_experiment(store, payload: dict) -> dict:
    payload = ExperimentInput.model_validate(payload).model_dump()
    with store.lock:
        brand = store.get("brands", payload["brand_id"])
        if not brand:
            raise KeyError("Brand not found.")
        if not brand.get("profile"):
            raise ValueError("Learn a brand voice before registering an experiment.")
        seed = secrets.randbits(128)
        rng = random.Random(seed)
        assignments = []
        # Each block contains all openings once, limiting imbalance over time.
        for _ in range(payload["slots_per_hook"]):
            block = list(HOOKS)
            rng.shuffle(block)
            assignments.extend(block)
        baseline = build_snapshot(store.list("posts"), store.list("feedback"), payload["brand_id"],
                                  payload["source"], payload["window"], 0, payload["platform"])
        identifier = str(uuid4())
        experiment = {
            **payload, "id": identifier, "registered_at": utcnow(), "metric": METRIC,
            "profile": deepcopy(brand["profile"]), "profile_version": brand["profile_version"],
            "baseline_snapshot": baseline, "randomization_seed": str(seed),
            "randomization_method": "Balanced randomized blocks of three opening styles, fixed before generation.",
            "slots": [{"id": str(uuid4()), "ordinal": i + 1, "hook": hook,
                       "run_id": None, "post_id": None} for i, hook in enumerate(assignments)],
            "analysis_ids": [], "comparison": None,
        }
        experiment["preregistration_hash"] = _plan_hash(experiment)
        store.put("experiments", experiment)
        return experiment_report(store, identifier)


def assignment_for_run(store, experiment_id: str, slot_id: str) -> dict:
    """Return trusted frozen overrides; call with the store lock when reserving."""
    with store.lock:
        experiment = _required(store, experiment_id)
        slot, comparison = _find_slot(experiment, slot_id)
        assignment = {
            "experiment_id": experiment_id, "experiment_slot_id": slot_id,
            "brand_id": experiment["brand_id"], "platform": experiment["platform"],
            "feedback_source": experiment["source"], "window": experiment["window"],
            "selected_hook": slot["hook"], "profile": deepcopy(experiment["profile"]),
            "profile_version": experiment["profile_version"],
            "use_learning": False, "learning_snapshot_id": None, "learning_version": 0,
            "evidence_ids": [], "existing_run_id": slot.get("run_id"),
            "experiment_baseline_snapshot_id": experiment["baseline_snapshot"]["id"],
            "experiment_baseline_snapshot": deepcopy(experiment["baseline_snapshot"]),
            "strategy_reason": f"Preregistered randomized experiment slot {slot['ordinal']}: {slot['hook']}. The assignment is fixed independently of outcomes.",
        }
        if comparison:
            enabled = slot["condition"] == "learning-on"
            assignment.update({key: deepcopy(comparison[key]) for key in (
                "brief", "mode", "contract", "model_preset", "manifest")})
            assignment.update({"comparison_id": comparison["id"], "comparison_condition": slot["condition"],
                               "generate_image": False, "use_learning": enabled,
                               "evidence_ids": experiment["baseline_snapshot"]["evidence_ids"] if enabled else [],
                               "strategy_reason": slot["reason"]})
        return assignment


def _after(first, second):
    try:
        return datetime.fromisoformat(first.replace("Z", "+00:00")) >= datetime.fromisoformat(second.replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError):
        return False


def prepare_binding(store, experiment_id: str, slot_id: str, run: dict, post: dict) -> dict:
    """Validate a fresh reservation and return its updated experiment without writes.

    The caller holds the store lock and commits the returned experiment with the
    matching run and post in one transaction, before a worker can observe it.
    """
    with store.lock:
        experiment = _required(store, experiment_id)
        slot, comparison = _find_slot(experiment, slot_id)
        run_id = run["id"]
        if slot.get("run_id"):
            if slot["run_id"] != run_id or slot.get("post_id") != run.get("post_id"):
                raise ValueError("This slot is already bound. Resume its original run instead of replacing it.")
            return experiment
        assignment = assignment_for_run(store, experiment_id, slot_id)
        for key in ("brand_id", "platform", "feedback_source", "window", "selected_hook", "profile", "profile_version",
                    "experiment_id", "experiment_slot_id"):
            if run.get(key) != assignment[key]:
                raise ValueError(f"The run must preserve the registered {key}.")
        required_mode = "demo" if experiment["source"] == "simulated" else "live"
        if run.get("mode") != required_mode:
            raise ValueError(f"The registered {experiment['source']} cohort requires {required_mode} generation.")
        boundary = comparison["registered_at"] if comparison else experiment["registered_at"]
        existing_run = store.get("runs", run_id)
        existing_post = store.get("posts", run["post_id"])
        if (not post or run.get("status") != "queued" or post.get("status") != "generating"
                or post.get("id") != run.get("post_id") or post.get("run_id") != run_id
                or post.get("brand_id") != assignment["brand_id"] or post.get("hook") != assignment["selected_hook"]
                or post.get("platform", "linkedin") != assignment["platform"]
                or post.get("published_at") or post.get("content")
                or (existing_run is not None and existing_run != run)
                or (existing_post is not None and existing_post != post)
                or not _after(run.get("created_at"), boundary)
                or not _after(post.get("created_at"), boundary)
                or store.list("feedback", post_id=run["post_id"])):
            raise ValueError("Only a newly reserved, unpublished run without outcomes can fill an experiment slot.")
        if comparison:
            for key in ("brief", "mode", "contract", "model_preset", "manifest"):
                expected = assignment[key]
                if key == "model_preset":
                    expected = expected or "configured"
                if run.get(key) != expected:
                    raise ValueError(f"Paired branches must preserve the frozen {key}.")
            if run.get("generate_image", False):
                raise ValueError("Paired branches must preserve text-only generation.")
        slot.update({"run_id": run_id, "post_id": run["post_id"], "bound_at": utcnow()})
        return experiment


def bind_run(store, experiment_id: str, slot_id: str, run: dict | str) -> dict:
    """Bind an already saved fresh reservation; completed historical posts stay invalid."""
    with store.lock:
        run_id = run if isinstance(run, str) else run["id"]
        actual = store.get("runs", run_id)
        if not actual:
            raise ValueError("Save the reserved run before binding it to an experiment.")
        post = store.get("posts", actual["post_id"])
        experiment = prepare_binding(store, experiment_id, slot_id, actual, post)
        slot, _ = _find_slot(experiment, slot_id)
        store.put("experiments", experiment)
        assignment = assignment_for_run(store, experiment_id, slot_id)
        store.add_event(actual["post_id"], "experiment", f"Reserved {slot['hook']}", assignment["strategy_reason"],
                        event_id=f"{experiment_id}:{slot_id}:reserved")
        return deepcopy(slot)


def _slot_state(store, experiment, slot):
    result = deepcopy(slot)
    result.update({"status": "pending", "reason": "Not generated yet; its fixed assignment remains in the report.",
                   "post_title": None, "opening": "", "content": "", "observation_ids": []})
    if not slot.get("run_id"):
        return result, None, []
    run = store.get("runs", slot["run_id"])
    post = store.get("posts", slot.get("post_id")) if slot.get("post_id") else None
    if not run or not post:
        result.update(status="excluded", reason="The bound run or post is missing; the assignment is retained.")
        return result, None, []
    result.update(post_title=post.get("title", ""), content=post.get("content", ""),
                  opening=post.get("content", "").split("\n", 1)[0])
    if run.get("status") in {"queued", "running", "failed", "interrupted"}:
        result.update(status=run["status"], reason=run.get("error") or "Generation has not completed. Its original run must be resumed after failure.")
        return result, None, []
    if post.get("hook") != slot["hook"] or post.get("brand_id") != experiment["brand_id"] or post.get("platform", "linkedin") != experiment["platform"]:
        result.update(status="excluded", reason="The published post no longer matches its registered assignment or scope.")
        return result, None, []
    if experiment["source"] == "manual" and post.get("is_demo"):
        result.update(status="excluded", reason="Simulated content cannot enter the manual audience cohort.")
        return result, None, []
    if post.get("status") not in {"published", "published_manually"}:
        result.update(status="awaiting_publish", reason="Generated but not confirmed published; no audience outcome is counted.")
        return result, None, []
    if not _after(post.get("published_at"), experiment["registered_at"]) or not _after(post.get("published_at"), run.get("created_at")):
        result.update(status="excluded", reason="Publication predates registration or draft reservation, or lacks a valid timestamp.")
        return result, None, []
    observations = store.list("feedback", post_id=post["id"])
    matching = [f for f in observations if f.get("source") == experiment["source"] and f.get("window") == experiment["window"]]
    if not matching:
        if observations:
            result.update(status="excluded", reason="Available observations do not match the registered provenance and window.",
                          observation_ids=[f.get("revision_id", f["id"]) for f in observations])
        else:
            result.update(status="awaiting_observation", reason="No observation has been recorded for the registered window.")
        return result, None, []
    # Keep the latest active observation in the rare case of legacy duplicate rows.
    observation = max(matching, key=lambda f: (f.get("captured_at", ""), f.get("revision", 0), f["id"]))
    result["observation_ids"] = [observation.get("revision_id", observation["id"])]
    reason = ("Missing or zero impressions." if observation.get("impressions", 0) <= 0 else
              "Measurement time does not establish the registered observation window."
              if experiment["source"] != "simulated" and observation.get("timing_status") != "window_matched" else None)
    if reason:
        result.update(status="excluded", reason=reason)
        return result, None, []
    result.update(status="eligible", reason="Matches the fixed assignment, provenance and observation window.")
    return result, post, [observation]


def _states(store, experiment):
    states, posts, feedback = [], [], []
    for slot in experiment["slots"]:
        state, post, observations = _slot_state(store, experiment, slot)
        states.append(state)
        if post:
            posts.append(post)
            feedback.extend(observations)
    return states, posts, feedback


def _counts(states):
    return {status: sum(slot["status"] == status for slot in states) for status in STATUSES}


def experiment_report(store, identifier: str) -> dict:
    with store.lock:
        experiment = _required(store, identifier)
        report = {key: deepcopy(value) for key, value in experiment.items() if key not in {"randomization_seed", "profile", "analysis_ids"}}
        report["slots"], _, _ = _states(store, experiment)
        report["counts"] = _counts(report["slots"])
        analyses = [store.get("experiment_analyses", item) for item in experiment["analysis_ids"]]
        analyses = [item for item in analyses if item]
        report["latest_analysis"] = analyses[-1] if analyses else None
        report["analyses"] = [{key: item[key] for key in ("id", "version", "created_at", "status")} for item in analyses]
        report["limitations"] = list(LIMITATIONS)
        if experiment.get("comparison"):
            report["comparison"] = {key: deepcopy(value) for key, value in experiment["comparison"].items() if key != "manifest"}
            report["comparison"]["branches"] = [_slot_state(store, experiment, branch)[0] for branch in experiment["comparison"]["branches"]]
        return report


def list_experiments(store, brand_id: str | None = None):
    with store.lock:
        records = store.list("experiments", **({"brand_id": brand_id} if brand_id else {}))
        return [experiment_report(store, item["id"]) for item in sorted(records, key=lambda item: item["registered_at"], reverse=True)]


def analyze_experiment(store, identifier: str) -> dict:
    with store.lock:
        experiment = _required(store, identifier)
        states, posts, feedback = _states(store, experiment)
        analysis = build_snapshot(posts, feedback, experiment["brand_id"], experiment["source"], experiment["window"],
                                  len(experiment["analysis_ids"]) + 1, experiment["platform"])
        complete = all(slot["status"] == "eligible" for slot in states)
        preferred = analysis["preferred_hook"] if complete else None
        analysis.update({"experiment_id": identifier, "preregistration_hash": experiment["preregistration_hash"],
                         "metric": METRIC, "slots": states, "counts": _counts(states), "complete_cohort": complete,
                         "preferred_hook": preferred, "status": "descriptive_signal" if preferred else "inconclusive",
                         "limitations": list(LIMITATIONS), "excluded": [
                             {"slot_id": slot["id"], "post_id": slot.get("post_id"), "status": slot["status"],
                              "reason": slot["reason"], "observation_ids": slot["observation_ids"]}
                             for slot in states if slot["status"] != "eligible"]})
        if preferred:
            stat = next(item for item in analysis["stats"] if item["hook"] == preferred)
            analysis["explanation"] = (f"Descriptive signal: {preferred} recorded {stat['rate']:.1f} {METRIC} with separated descriptive ranges. "
                                       "All assigned outcomes are present. This is an observed association, not causal uplift or proof of a better opening.")
        elif not complete:
            analysis["explanation"] = (f"Inconclusive: {sum(slot['status'] == 'eligible' for slot in states)} of {len(states)} assigned slots have comparable outcomes. "
                                       "Pending, failed, unpublished, missing and excluded slots remain visible; no preference is declared from an incomplete cohort.")
        elif not all(item["sufficient"] for item in analysis["stats"]):
            analysis["explanation"] = (f"Inconclusive: require at least {MIN_POSTS} published posts and {MIN_IMPRESSIONS} impressions for each opening. "
                                       "A smaller registered experiment is a workflow pilot and cannot produce a preference.")
        else:
            analysis["explanation"] = "Inconclusive: the observed descriptive ranges overlap or tie. There is no clear preference in this cohort."
        experiment["analysis_ids"].append(analysis["id"])
        store.put_many([("experiment_analyses", analysis), ("experiments", experiment)])
        return deepcopy(analysis)


def create_comparison(store, settings, identifier: str, payload: dict) -> dict:
    """Freeze one pair before either run exists; retries reuse this exact pair."""
    from .pipeline import create_run_manifest
    from .contracts import validate_contract
    payload = SlotRunInput.model_validate(payload).model_dump()
    if payload["generate_image"]:
        raise ValueError("Matched draft comparisons generate text only.")
    with store.lock:
        experiment = _required(store, identifier)
        payload["contract"] = validate_contract(payload.get("contract") or {}, experiment["platform"])
        mode = "demo" if experiment["source"] == "simulated" else "live"
        if payload["mode"] != mode:
            raise ValueError(f"The registered cohort requires {mode} generation.")
        existing = experiment.get("comparison")
        if existing:
            if any(existing.get(key) != payload[key] for key in ("brief", "mode", "contract", "model_preset")):
                raise ValueError("This experiment already has a fixed comparison. Its brief, contract, mode and models cannot be replaced.")
            return deepcopy(existing)
        preset = payload["model_preset"]
        if preset:
            settings = replace(settings, chat_model={"budget": "openai/gpt-4o-mini", "submission-tested": "openai/gpt-5.1"}[preset])
        branches = []
        for i, enabled in enumerate((False, True)):
            hook, reason = select_hook(experiment["baseline_snapshot"] if enabled else None, 0)
            condition = "learning-on" if enabled else "learning-off"
            branches.append({"id": f"comparison-{condition}", "ordinal": i + 1, "condition": condition,
                             "hook": hook, "reason": f"Matched {condition} branch using the frozen registration baseline. {reason}",
                             "run_id": None, "post_id": None})
        comparison = {"id": str(uuid4()), "registered_at": utcnow(), **payload,
                      "manifest": create_run_manifest(settings, platform=experiment["platform"]), "branches": branches,
                      "note": "Same brief, frozen voice, contract and model settings. Generation is stochastic; comparing these drafts is not evidence of audience uplift.",
                      "policy_contrast": branches[0]["hook"] != branches[1]["hook"]}
        comparison["registration_hash"] = _comparison_hash(comparison)
        experiment["comparison"] = comparison
        store.put("experiments", experiment)
        return deepcopy(comparison)


def build_router(create_run_fn, resume_run_fn=None) -> APIRouter:
    """Mount with the app's guarded creation callback and optional resume guard."""
    router = APIRouter(prefix="/api/experiments", tags=["experiments"])

    def invoke(fn, *args):
        try:
            return fn(*args)
        except KeyError as error:
            raise HTTPException(404, str(error).strip("'")) from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @router.post("", status_code=201)
    def register(payload: ExperimentInput, request: Request):
        return invoke(create_experiment, request.app.state.store, payload.model_dump())

    @router.get("")
    def listing(request: Request, brand_id: str | None = None):
        return invoke(list_experiments, request.app.state.store, brand_id)

    @router.get("/{experiment_id}")
    def detail(experiment_id: str, request: Request):
        return invoke(experiment_report, request.app.state.store, experiment_id)

    @router.post("/{experiment_id}/analyze", status_code=201)
    def analyze(experiment_id: str, request: Request):
        return invoke(analyze_experiment, request.app.state.store, experiment_id)

    @router.get("/{experiment_id}/analyses/{analysis_id}")
    def saved_analysis(experiment_id: str, analysis_id: str, request: Request):
        store = request.app.state.store
        experiment = invoke(_required, store, experiment_id)
        if analysis_id not in experiment["analysis_ids"]:
            raise HTTPException(404, "Analysis not found for this experiment.")
        return store.get("experiment_analyses", analysis_id)

    def start_slot(request, experiment_id, slot_id, payload):
        store = request.app.state.store
        with store.lock:
            assignment = invoke(assignment_for_run, store, experiment_id, slot_id)
            existing_id = assignment.get("existing_run_id")
            if existing_id:
                existing = store.get("runs", existing_id)
                if not existing:
                    raise HTTPException(409, "The original run is missing; this assignment cannot be rerolled.")
                if resume_run_fn and existing.get("status") in {"failed", "interrupted"}:
                    return resume_run_fn(existing_id)
                return existing
            required_mode = "demo" if assignment["feedback_source"] == "simulated" else "live"
            if payload.mode != required_mode:
                raise HTTPException(409, f"The registered cohort requires {required_mode} generation.")
            if len([run for run in store.list("runs") if run.get("status") in {"queued", "running"}]) >= 3:
                raise HTTPException(429, "Three runs are already queued. Let one finish before starting another.")
            body = {**payload.model_dump(), **{key: assignment[key] for key in (
                "brand_id", "platform", "feedback_source", "window", "use_learning", "experiment_id", "experiment_slot_id")}}
            return invoke(create_run_fn, store, request.app.state.settings, body)

    @router.post("/{experiment_id}/slots/{slot_id}/run", status_code=202)
    def run_slot(experiment_id: str, slot_id: str, payload: SlotRunInput, request: Request):
        return start_slot(request, experiment_id, slot_id, payload)

    @router.post("/{experiment_id}/comparisons", status_code=202)
    def matched_comparison(experiment_id: str, payload: SlotRunInput, request: Request):
        store = request.app.state.store
        with store.lock:
            comparison = invoke(create_comparison, store, request.app.state.settings, experiment_id, payload.model_dump())
            for branch in comparison["branches"]:
                start_slot(request, experiment_id, branch["id"], payload)
            return experiment_report(store, experiment_id)["comparison"]

    return router

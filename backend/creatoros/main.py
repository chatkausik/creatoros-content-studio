"""Local HTTP API and React application host."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError, field_validator

from .config import ROOT, Settings, load_settings
from .fixtures import seed_demo
from .feedback import FeedbackInput, FeedbackError, prepare_feedback
from .contracts import Contract, check_contract, suggest_contract
from .feedback_imports import router as feedback_import_router
from .learning import HOOKS
from .service import create_run, hydrate_post, learn, process_due_posts
from .store import Store, utcnow

logger = logging.getLogger("creatoros")
Mode = Literal["demo", "live"]
Source = Literal["manual", "simulated"]
Window = Literal["24h", "7d"]
Platform = Literal["linkedin", "newsletter"]


class Sample(BaseModel):
    text: str = Field(min_length=30, max_length=12000)
    source: str = Field(default="User-provided sample", max_length=2000)


class BrandInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    samples: list[Sample] = Field(min_length=3, max_length=20)

    @field_validator("samples")
    @classmethod
    def distinct_samples(cls, value):
        if len({s.text.strip() for s in value}) < 3:
            raise ValueError("Provide at least three different writing samples.")
        return value


class ModeInput(BaseModel):
    mode: Mode = "live"


class ImageInput(ModeInput):
    regenerate: bool = False
    new_attempt: bool = False
    feedback: str = Field(default="", max_length=1200)


class ImageSelection(BaseModel):
    variant_id: str


class EditInput(BaseModel):
    content: str = Field(min_length=20, max_length=12000)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    reason: str = Field(min_length=5, max_length=1200)


class ApprovalInput(BaseModel):
    acknowledge_unresolved: bool = False


class RunInput(BaseModel):
    brand_id: str
    brief: str = Field(min_length=10, max_length=6000)
    mode: Mode = "demo"
    use_learning: bool = True
    feedback_source: Source = "simulated"
    window: Window = "24h"
    generate_image: bool = False
    platform: Platform = "linkedin"
    model_preset: Literal["budget", "submission-tested"] | None = None
    contract: Contract = Field(default_factory=Contract)


class ContractSuggestionInput(BaseModel):
    brief: str = Field(min_length=1, max_length=6000)
    platform: Platform = "linkedin"


class ScheduleInput(BaseModel):
    scheduled_at: datetime

    @field_validator("scheduled_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("Include a timezone in the scheduled time.")
        if value <= datetime.now(timezone.utc):
            raise ValueError("Choose a future scheduled time.")
        return value.astimezone(timezone.utc)


class PublishInput(BaseModel):
    published_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("published_at")
    @classmethod
    def valid_time(cls, value):
        if value.tzinfo is None:
            raise ValueError("Include a timezone in the published time.")
        if value > datetime.now(timezone.utc):
            raise ValueError("Published time cannot be in the future.")
        return value.astimezone(timezone.utc)




class LearnInput(BaseModel):
    source: Source = "manual"
    window: Window = "24h"
    platform: Platform = "linkedin"


class ImportInput(PublishInput):
    brand_id: str
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=20, max_length=12000)
    hook: Literal["problem-first", "outcome-first", "question-first"]
    source: Literal["manual"] = "manual"
    source_url: str = Field(default="", max_length=2000)
    platform: Platform = "linkedin"


def read_evaluation():
    reports = [ROOT / "evals" / name / "results.json" for name in ("fresh-recovered", "fresh")]
    path = next((report for report in reports if report.exists()), ROOT / "evals" / "results.json")
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (ValueError, OSError):
            logger.warning("Evaluation results could not be read.")
    return {"status": "not_run", "cases": [], "summary": {}, "limitations": ["Run scripts/evaluate.py to produce measured results."]}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    image_locks: dict[str, asyncio.Lock] = {}
    profile_locks: dict[str, asyncio.Lock] = {}
    review_locks: dict[str, asyncio.Lock] = {}

    async def worker(store):
        from .pipeline import run_pipeline
        while True:
            process_due_posts(store)
            queued = sorted(store.list("runs", status="queued"), key=lambda r: r.get("created_at", ""))
            if queued:
                run = queued[0]
                try:
                    await run_pipeline(run["id"], store, settings)
                except asyncio.CancelledError:
                    current = store.get("runs", run["id"])
                    if current and current["status"] not in {"complete", "failed"}:
                        store.patch("runs", run["id"], {"status": "interrupted", "error": "Application stopped. Resume this run to continue."})
                    raise
                except Exception:
                    logger.error("Run %s stopped. Inspect its persisted artifacts before retrying.", run["id"])
                    store.patch("runs", run["id"], {"status": "failed", "error": "Generation failed. Check the Mesh configuration and resume the run."})
            await asyncio.sleep(0.5)

    async def scheduler(store):
        while True:
            process_due_posts(store)
            await asyncio.sleep(5)

    @asynccontextmanager
    async def lifespan(app):
        store = Store(settings.data_dir)
        app.state.store = store
        app.state.settings = settings
        if settings.seed_demo:
            seed_demo(store)
        for run in store.list("runs"):
            if run["status"] == "running":
                store.patch("runs", run["id"], {"status": "interrupted", "error": "A previous session stopped. Resume to continue from saved work."})
        process_due_posts(store)
        tasks = [asyncio.create_task(worker(store)), asyncio.create_task(scheduler(store))] if settings.worker_enabled else []
        yield
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        store.close()

    app = FastAPI(title="CreatorOS", version="1.0.0", lifespan=lifespan)
    app.include_router(feedback_import_router)
    from .experiments import build_router
    app.include_router(build_router(create_run))
    app.add_middleware(CORSMiddleware, allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"
    ], allow_methods=["GET", "POST", "PUT"], allow_headers=["Content-Type"])

    @app.middleware("http")
    async def local_origin_only(request: Request, call_next):
        # Local app has no account authentication. Reject cross-site writes so
        # an unrelated web page cannot trigger paid generation against localhost.
        origin = request.headers.get("origin")
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and origin:
            if origin not in {"http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"}:
                return JSONResponse({"detail": "Cross-site writes to the local studio are not allowed."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    def db():
        return app.state.store

    def required(collection, identifier):
        obj = db().get(collection, identifier)
        if obj is None:
            raise HTTPException(404, "Record not found.")
        return obj

    def require_idle_post(post):
        """Call under the store lock before committing a workflow transition."""
        post_id = post["id"]
        run = db().get("runs", post.get("run_id")) if post.get("run_id") else None
        if ((run and run["status"] in {"queued", "running"})
                or image_locks.get(post_id, asyncio.Lock()).locked()
                or review_locks.get(post_id, asyncio.Lock()).locked()):
            raise HTTPException(409, "Wait for the active generation, review or visual request before scheduling or confirming publication.")

    def current_action_draft(original):
        """Revalidate after an await; never overwrite a newer workflow decision."""
        current = required("posts", original["id"])
        run = db().get("runs", current.get("run_id")) if current.get("run_id") else None
        watched = ("status", "content", "title", "versions", "reviews", "approved_at", "scheduled_at", "published_at")
        if (current["status"] not in {"draft", "needs_review", "approved"}
                or any(current.get(key) != original.get(key) for key in watched)
                or (run and run["status"] in {"queued", "running"})):
            raise HTTPException(409, "The post changed while this action was running. Its current content and publishing decision were preserved; reopen it before retrying.")
        return current

    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "creatoros", "version": "1.0.0"}

    @app.post("/api/contracts/suggest")
    def suggest_rules(payload: ContractSuggestionInput):
        return suggest_contract(payload.brief, payload.platform)

    @app.get("/api/bootstrap")
    def bootstrap():
        store = db()
        return {
            "brands": sorted(store.list("brands"), key=lambda b: (b.get("is_demo", False), b["name"])),
            "posts": [hydrate_post(store, p) for p in sorted(store.list("posts"), key=lambda p: p["created_at"], reverse=True)],
            "snapshots": store.list("snapshots"),
            "runs": [{k: v for k, v in r.items() if k not in {"artifacts", "profile"}} for r in store.list("runs")],
            "settings": {"mesh_configured": bool(settings.mesh_api_key), "chat_model": settings.chat_model,
                         "image_model": settings.image_model, "mode": "local", "platform": "LinkedIn",
                         "platforms": ["linkedin", "newsletter"],
                         "model_presets": {"budget": "openai/gpt-4o-mini", "submission-tested": "openai/gpt-5.1"}},
            "evaluation": read_evaluation(),
        }

    @app.post("/api/brands", status_code=201)
    def add_brand(payload: BrandInput):
        return db().put("brands", {
            "id": str(uuid4()), **payload.model_dump(), "is_demo": False,
            "profile": None, "profile_version": 0, "created_at": utcnow(),
        })

    @app.post("/api/brands/{brand_id}/profile")
    async def profile(brand_id: str, payload: ModeInput):
        from .pipeline import extract_profile
        brand = required("brands", brand_id)
        if payload.mode == "live" and not settings.mesh_api_key:
            raise HTTPException(400, "Set MESH_API_KEY in your local .env first.")
        lock = profile_locks.setdefault(brand_id, asyncio.Lock())
        if lock.locked():
            raise HTTPException(409, "Voice learning is already in progress.")
        async with lock:
            try:
                result = await extract_profile(brand["samples"], settings, mode=payload.mode)
            except Exception:
                raise HTTPException(502, "Could not learn this voice through Mesh. Check the configured model and available credits, then retry.") from None
            version = brand["profile_version"] + 1
            db().put("profiles", {"id": f"{brand_id}:v{version}", "brand_id": brand_id,
                                  "version": version, "profile": result, "source": payload.mode, "created_at": utcnow()})
            return db().patch("brands", brand_id, {"profile": result, "profile_version": version, "profile_source": payload.mode})

    @app.post("/api/runs", status_code=202)
    def start_run(payload: RunInput):
        active = [r for r in db().list("runs") if r["status"] in {"queued", "running"}]
        if len(active) >= 3:
            raise HTTPException(429, "Three runs are already queued. Let one finish before starting another.")
        try:
            return create_run(db(), settings, payload.model_dump())
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.get("/api/runs/{run_id}")
    def read_run(run_id: str):
        run = required("runs", run_id)
        return {"run": run, "post": hydrate_post(db(), required("posts", run["post_id"]))}

    @app.post("/api/runs/{run_id}/resume", status_code=202)
    def resume(run_id: str):
        with db().lock:
            run = required("runs", run_id)
            if run["status"] not in {"failed", "interrupted"}:
                raise HTTPException(409, "Only failed or interrupted runs can be resumed.")
            post_id = run["post_id"]
            if image_locks.get(post_id, asyncio.Lock()).locked() or review_locks.get(post_id, asyncio.Lock()).locked():
                raise HTTPException(409, "Finish the active visual or editorial action before resuming generation.")
            post = required("posts", post_id)
            human_versions = any(v.get("kind") in {"human_edit", "manual_edit"} or v.get("source") == "human"
                                 for v in post.get("versions", []))
            manual_reviews = any(r.get("review_action") == "manual" or r.get("content_sha256")
                                 or r.get("reviewed_content_sha256") for r in post.get("reviews", []))
            human_decisions = any(e.get("node") == "human" or e.get("choice") in {
                "Reviewed the edited draft", "Created a matching visual"
            } for e in db().list("events", post_id=post_id))
            manual_visuals = any(v.get("id") != f"{run_id}:image:initial" for v in post.get("image_variants", []))
            if (post["status"] not in {"generating", "draft", "needs_review"}
                    or any(post.get(key) for key in ("approved_at", "scheduled_at", "published_at", "pending_image_request"))
                    or human_versions or manual_reviews or human_decisions or manual_visuals):
                raise HTTPException(409, "This post has changes or publishing decisions made after generation. Resume would replace that work. Keep this post and start a new draft instead.")
            if len([r for r in db().list("runs") if r["status"] in {"queued", "running"}]) >= 3:
                raise HTTPException(429, "Three runs are already queued. Let one finish before resuming another.")
            return db().patch("runs", run_id, {"status": "queued", "error": None})

    @app.get("/api/posts/{post_id}")
    def read_post(post_id: str):
        return hydrate_post(db(), required("posts", post_id))

    @app.post("/api/posts/{post_id}/image")
    async def image(post_id: str, payload: ImageInput):
        from .pipeline import create_run_manifest, frozen_settings, generate_visual
        from .mesh import MeshError
        post = required("posts", post_id)
        if not post.get("content"):
            raise HTTPException(409, "Finish the draft before generating its visual.")
        if post["status"] not in {"draft", "needs_review", "approved"}:
            raise HTTPException(409, "Generate the image before scheduling or publishing.")
        run = db().get("runs", post.get("run_id")) if post.get("run_id") else None
        if run and run["status"] in {"queued", "running"}:
            raise HTTPException(409, "Wait for generation to finish before changing the image.")
        lock = image_locks.setdefault(post_id, asyncio.Lock())
        if lock.locked():
            raise HTTPException(409, "An image is already being generated for this post.")
        async with lock:
            with db().lock:
                post = current_action_draft(post)
                if review_locks.get(post_id, asyncio.Lock()).locked():
                    raise HTTPException(409, "Finish the active editorial review before changing the image.")
                if post.get("image_url") and not payload.regenerate and not post.get("image_stale") and not post.get("pending_image_request") and (payload.mode == "demo" or post.get("image_source") == "mesh"):
                    return hydrate_post(db(), post)
                content_hash = hashlib.sha256(post["content"].encode()).hexdigest()
                pending = post.get("pending_image_request") or {}
                if payload.new_attempt or pending.get("content_sha256") != content_hash or pending.get("feedback") != payload.feedback or pending.get("mode") != payload.mode:
                    pending = {"id": str(uuid4()), "content_sha256": content_hash, "feedback": payload.feedback,
                               "mode": payload.mode, "manifest": create_run_manifest(settings, post.get("platform", "linkedin"))}
                pending.setdefault("manifest", create_run_manifest(settings, post.get("platform", "linkedin")))
                db().patch("posts", post_id, {"pending_image_request": pending})
            # A newly requested visual is a new action, not a resumed old text run.
            try:
                image_settings = frozen_settings(settings, pending["manifest"])
                result = await generate_visual(post, image_settings, mode=payload.mode,
                                               feedback=payload.feedback, regeneration_id=pending["id"])
            except MeshError as error:
                db().patch("posts", post_id, {"image_error": {"message": str(error), "diagnostics": error.diagnostics,
                                                              "request_id": pending["id"], "created_at": utcnow()}})
                raise HTTPException(502, str(error)) from None
            except Exception:
                raise HTTPException(502, "Image generation failed. The text is saved. Check Mesh image-model access and credits before retrying.") from None
            variant = {"id": pending["id"], "url": result["image_url"], "source": result.get("source", payload.mode),
                       "feedback": payload.feedback, "created_at": utcnow(), "prompt": result.get("image_prompt"),
                       "model": result.get("model"), "actual_model": result.get("actual_model"),
                       "usage": result.get("usage", []), "content_sha256": content_hash,
                       "asset_sha256": result.get("asset_sha256") or result.get("content_sha256"),
                       "request_id": result.get("request_id", pending["id"]), "reason": result.get("reason"),
                       "manifest": pending["manifest"]}
            with db().lock:
                post = current_action_draft(post)
                variants = hydrate_post(db(), post).get("image_variants", [])
                variants.append(variant)
                updated = db().patch("posts", post_id, {
                    "image_url": result["image_url"], "image_prompt": result.get("image_prompt"),
                    "image_model": result.get("model"), "image_source": result.get("source", payload.mode),
                    "image_variants": variants, "selected_image_variant_id": variant["id"],
                    "image_stale": False, "pending_image_request": None, "image_error": None, "approved_at": None,
                    "status": "draft" if post["status"] == "approved" else post["status"],
                })
            db().add_event(post_id, "visual", "Created a matching visual", result.get("image_prompt", "Matched the illustration to the post."), [variant["id"]], event_id=f"image:{post_id}:{variant['id']}")
            return hydrate_post(db(), updated)

    @app.post("/api/posts/{post_id}/image/select")
    def select_image(post_id: str, payload: ImageSelection):
        with db().lock:
            post = required("posts", post_id)
            run = db().get("runs", post.get("run_id")) if post.get("run_id") else None
            if image_locks.get(post_id, asyncio.Lock()).locked() or review_locks.get(post_id, asyncio.Lock()).locked() or (run and run["status"] in {"queued", "running"}):
                raise HTTPException(409, "Finish the active generation or review before selecting an image.")
            if post["status"] not in {"draft", "needs_review", "approved"}:
                raise HTTPException(409, "Choose an image before scheduling or publishing.")
            variants = hydrate_post(db(), post).get("image_variants", [])
            variant = next((v for v in variants if v["id"] == payload.variant_id), None)
            if not variant:
                raise HTTPException(404, "Image version not found.")
            content_hash = hashlib.sha256(post["content"].encode()).hexdigest()
            result = db().patch("posts", post_id, {"image_variants": variants, "selected_image_variant_id": variant["id"],
                "image_url": variant["url"], "image_source": variant["source"], "image_prompt": variant.get("prompt"),
                "image_model": variant.get("model"), "image_stale": bool(variant.get("content_sha256") and variant["content_sha256"] != content_hash),
                "approved_at": None, "status": "draft" if post["status"] == "approved" else post["status"]})
            db().add_event(post_id, "human", "Selected image version", f"Selected saved variant {variant['id']}.", [variant["id"]])
            return hydrate_post(db(), result)

    @app.post("/api/posts/{post_id}/edit")
    def edit_post(post_id: str, payload: EditInput):
        with db().lock:
            post = required("posts", post_id)
            if post["status"] not in {"draft", "needs_review", "approved"}:
                raise HTTPException(409, "Edit a completed draft before scheduling or publishing.")
            run = db().get("runs", post.get("run_id")) if post.get("run_id") else None
            if (run and run["status"] in {"running", "queued"}) or image_locks.get(post_id, asyncio.Lock()).locked() or review_locks.get(post_id, asyncio.Lock()).locked():
                raise HTTPException(409, "Wait for the active generation or review to finish before editing.")
            if post.get("platform", "linkedin") == "linkedin" and len(payload.content) > 3000:
                raise HTTPException(422, "LinkedIn content must be at most 3,000 characters.")
            versions = list(post.get("versions", []))
            contract_checks = check_contract(payload.content, post.get("contract"))
            versions.append({"id": str(uuid4()), "version": len(versions) + 1, "content": payload.content,
                             "title": payload.title or post["title"], "kind": "human_edit", "source": "human",
                             "reason": payload.reason, "created_at": utcnow(), "contract_checks": contract_checks})
            changes = {"content": payload.content, "versions": versions, "review_stale": True,
                       "image_stale": bool(post.get("image_url")), "status": "needs_review", "approved_at": None,
                       "contract_checks": contract_checks}
            if payload.title:
                changes["title"] = payload.title
            result = db().patch("posts", post_id, changes)
            db().add_event(post_id, "human", "Edited the draft", payload.reason)
            return hydrate_post(db(), result)

    @app.post("/api/posts/{post_id}/review")
    async def review_edited_post(post_id: str, payload: ModeInput):
        from .pipeline import create_run_manifest, review_post
        post = required("posts", post_id)
        if post["status"] not in {"draft", "needs_review", "approved"}:
            raise HTTPException(409, "Review a completed draft before scheduling or publishing.")
        lock = review_locks.setdefault(post_id, asyncio.Lock())
        if lock.locked():
            raise HTTPException(409, "This post is already being reviewed.")
        run = db().get("runs", post.get("run_id")) if post.get("run_id") else None
        if run and run["status"] in {"queued", "running"}:
            raise HTTPException(409, "Wait for generation to finish before requesting a new review.")
        async with lock:
            with db().lock:
                post = current_action_draft(post)
                if image_locks.get(post_id, asyncio.Lock()).locked():
                    raise HTTPException(409, "Finish the active visual request before reviewing this draft.")
            brand = required("brands", post["brand_id"])
            try:
                result = await review_post(post, (run or {}).get("profile") or brand.get("profile", {}), settings, payload.mode)
            except ValidationError as error:
                raise HTTPException(422, "Draft does not meet the platform's review requirements: " + "; ".join(item["msg"] for item in error.errors(include_input=False))) from None
            except Exception:
                raise HTTPException(502, "Could not complete the editorial review. Your text and earlier reviews are saved.") from None
            result["content_sha256"] = hashlib.sha256(post["content"].encode()).hexdigest()
            result["manifest"] = create_run_manifest(settings, post.get("platform", "linkedin"))
            result["version"] = len(post.get("versions", []))
            result["review_action"] = "manual"
            with db().lock:
                post = current_action_draft(post)
                updated = db().patch("posts", post_id, {"reviews": [*post.get("reviews", []), result],
                    "review_stale": False, "status": "draft" if result.get("approved") else "needs_review", "approved_at": None})
            db().add_event(post_id, "editor", "Reviewed the edited draft", "A new review is linked to the current text; previous reviews remain historical.")
            return hydrate_post(db(), updated)

    @app.post("/api/posts/{post_id}/approve")
    def approve(post_id: str, payload: ApprovalInput = ApprovalInput()):
        with db().lock:
            post = required("posts", post_id)
            run = db().get("runs", post.get("run_id")) if post.get("run_id") else None
            if run and run["status"] in {"queued", "running"}:
                raise HTTPException(409, "Wait for generation to finish before approving this draft.")
            if review_locks.get(post_id, asyncio.Lock()).locked() or image_locks.get(post_id, asyncio.Lock()).locked():
                raise HTTPException(409, "Wait for the current review or visual generation to finish before approval.")
            if post["status"] not in {"draft", "needs_review", "approved"} or not post.get("content"):
                raise HTTPException(409, "Only completed drafts can be approved.")
            contract_checks = check_contract(post["content"], post.get("contract"))
            if contract_checks["passed"] is False:
                raise HTTPException(409, "This draft does not meet its agreed brief contract. Edit the text to resolve: " + "; ".join(contract_checks["violations"]))
            if post.get("platform") == "newsletter":
                from .schemas import NewsletterDraft
                try:
                    NewsletterDraft.model_validate({"title": post["title"], "content": post["content"]})
                except ValidationError as error:
                    raise HTTPException(409, "This newsletter does not meet its platform requirements. " + "; ".join(item["msg"] for item in error.errors(include_input=False))) from None
            if post["status"] == "approved":
                return hydrate_post(db(), post)
            latest_review = (post.get("reviews") or [None])[-1]
            editorial_concerns = bool(latest_review and (
                not latest_review.get("approved")
                or latest_review.get("requests")
                or latest_review.get("requires_human_review")
            ))
            if (post["status"] == "needs_review" or post.get("review_stale") or post.get("image_stale") or editorial_concerns) and not payload.acknowledge_unresolved:
                raise HTTPException(409, "Review the unresolved editorial or visual concerns and explicitly acknowledge them before approval.")
            result = db().patch("posts", post_id, {"status": "approved", "approved_at": utcnow()})
            db().add_event(post_id, "human", "Approved for scheduling", "The creator reviewed and approved the content." + (" Unresolved or stale checks were explicitly acknowledged." if payload.acknowledge_unresolved else ""))
            return hydrate_post(db(), result)

    @app.post("/api/posts/{post_id}/schedule")
    def schedule(post_id: str, payload: ScheduleInput):
        with db().lock:
            post = required("posts", post_id)
            require_idle_post(post)
            if post["status"] not in {"approved", "scheduled", "ready_to_publish"}:
                raise HTTPException(409, "Approve this post before scheduling it.")
            if not post.get("image_url"):
                raise HTTPException(409, "Generate a matching visual before scheduling the finished post.")
            when = payload.scheduled_at.isoformat()
            result = db().patch("posts", post_id, {"status": "scheduled", "scheduled_at": when})
        db().add_event(post_id, "scheduler", "Queued for publication", f"Scheduled for {when}. Publication requires manual confirmation.")
        return hydrate_post(db(), result)

    @app.post("/api/posts/{post_id}/publish")
    def publish(post_id: str, payload: PublishInput):
        with db().lock:
            post = required("posts", post_id)
            require_idle_post(post)
            if post["status"] not in {"approved", "scheduled", "ready_to_publish", "published_manually"}:
                raise HTTPException(409, "Approve the post before confirming publication.")
            if post["status"] == "published_manually":
                return hydrate_post(db(), post)
            result = db().patch("posts", post_id, {"status": "published_manually", "published_at": payload.published_at.isoformat()})
        db().add_event(post_id, "human", "Publication confirmed manually", "The creator marked this post as published. CreatorOS did not call a platform publishing API.")
        return hydrate_post(db(), result)

    @app.post("/api/posts/import", status_code=201)
    def import_post(payload: ImportInput):
        required("brands", payload.brand_id)
        data = payload.model_dump(mode="json")
        post = {**data, "id": str(uuid4()), "brief": payload.title, "status": "published_manually",
                "is_demo": False, "created_at": utcnow(), "scheduled_at": None, "image_url": None,
                "original_draft": payload.content, "profile_version": 0, "learning_version": 0,
                "run_id": None, "versions": [{"version": 1, "content": payload.content, "kind": "imported"}], "reviews": []}
        db().put("posts", post)
        db().add_event(post["id"], "import", "Imported published content", "Creator-provided content and hook classification. Metrics are recorded separately.")
        return hydrate_post(db(), post)

    @app.put("/api/posts/{post_id}/feedback")
    def feedback(post_id: str, payload: FeedbackInput):
        with db().lock:
            post = required("posts", post_id)
            try:
                observation, records = prepare_feedback(db(), post, payload)
            except FeedbackError as error:
                raise HTTPException(error.status_code, str(error)) from None
            db().put_many(records)
            return observation

    @app.post("/api/brands/{brand_id}/learn")
    def learning(brand_id: str, payload: LearnInput):
        required("brands", brand_id)
        return learn(db(), brand_id, payload.source, payload.window, payload.platform)

    @app.get("/api/evaluation")
    def evaluation():
        return read_evaluation()

    # Serve assets without exposing SQLite, imports, configuration, or credentials.
    (settings.data_dir / "assets").mkdir(parents=True, exist_ok=True)
    app.mount("/assets", StaticFiles(directory=settings.data_dir / "assets"), name="assets")
    frontend = ROOT / "frontend" / "dist"
    if (frontend / "static").is_dir():
        app.mount("/static", StaticFiles(directory=frontend / "static"), name="frontend-assets")

    @app.get("/{path:path}")
    def frontend_route(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "API endpoint not found.")
        candidate = (frontend / path).resolve()
        if frontend.resolve() in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        index = frontend / "index.html"
        if index.exists():
            return FileResponse(index)
        return JSONResponse({"message": "CreatorOS API is running. Build the UI with npm --prefix frontend run build, or start the Vite development server.", "docs": "/docs"})

    return app


app = create_app()

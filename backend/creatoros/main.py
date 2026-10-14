"""Local HTTP API and React application host."""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .config import ROOT, Settings, load_settings
from .fixtures import seed_demo
from .learning import HOOKS
from .service import create_run, hydrate_post, learn, process_due_posts
from .store import Store, utcnow

logger = logging.getLogger("creatoros")
Mode = Literal["demo", "live"]
Source = Literal["manual", "simulated"]
Window = Literal["24h", "7d"]


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


class RunInput(BaseModel):
    brand_id: str
    brief: str = Field(min_length=10, max_length=6000)
    mode: Mode = "demo"
    use_learning: bool = True
    feedback_source: Source = "simulated"
    window: Window = "24h"
    generate_image: bool = False


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


class FeedbackInput(BaseModel):
    impressions: int = Field(ge=0, le=10**12, strict=True)
    reactions: int = Field(default=0, ge=0, le=10**12, strict=True)
    comments: int = Field(default=0, ge=0, le=10**12, strict=True)
    reposts: int = Field(default=0, ge=0, le=10**12, strict=True)
    window: Window = "24h"
    source: Source = "manual"


class LearnInput(BaseModel):
    source: Source = "manual"
    window: Window = "24h"


class ImportInput(PublishInput):
    brand_id: str
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=20, max_length=12000)
    hook: Literal["problem-first", "outcome-first", "question-first"]
    source: Literal["manual"] = "manual"
    source_url: str = Field(default="", max_length=2000)


def read_evaluation():
    path = ROOT / "evals" / "results.json"
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

    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "creatoros", "version": "1.0.0"}

    @app.get("/api/bootstrap")
    def bootstrap():
        store = db()
        return {
            "brands": sorted(store.list("brands"), key=lambda b: (b.get("is_demo", False), b["name"])),
            "posts": [hydrate_post(store, p) for p in sorted(store.list("posts"), key=lambda p: p["created_at"], reverse=True)],
            "snapshots": store.list("snapshots"),
            "runs": [{k: v for k, v in r.items() if k not in {"artifacts", "profile"}} for r in store.list("runs")],
            "settings": {"mesh_configured": bool(settings.mesh_api_key), "chat_model": settings.chat_model,
                         "image_model": settings.image_model, "mode": "local", "platform": "LinkedIn"},
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
        run = required("runs", run_id)
        if run["status"] not in {"failed", "interrupted"}:
            raise HTTPException(409, "Only failed or interrupted runs can be resumed.")
        return db().patch("runs", run_id, {"status": "queued", "error": None})

    @app.get("/api/posts/{post_id}")
    def read_post(post_id: str):
        return hydrate_post(db(), required("posts", post_id))

    @app.post("/api/posts/{post_id}/image")
    async def image(post_id: str, payload: ModeInput):
        from .pipeline import generate_visual
        post = required("posts", post_id)
        if not post.get("content"):
            raise HTTPException(409, "Finish the draft before generating its visual.")
        if post["status"] not in {"draft", "needs_review", "approved"}:
            raise HTTPException(409, "Generate the image before scheduling or publishing.")
        lock = image_locks.setdefault(post_id, asyncio.Lock())
        if lock.locked():
            raise HTTPException(409, "An image is already being generated for this post.")
        async with lock:
            if post.get("image_url") and (payload.mode == "demo" or post.get("image_source") == "mesh"):
                return hydrate_post(db(), post)
            try:
                result = await generate_visual(post, settings, mode=payload.mode)
            except Exception:
                raise HTTPException(502, "Image generation failed. The text is saved. Check Mesh image-model access and credits before retrying.") from None
            updated = db().patch("posts", post_id, {
                "image_url": result["image_url"], "image_prompt": result.get("image_prompt"),
                "image_model": result.get("model"), "image_source": result.get("source", payload.mode),
            })
            db().add_event(post_id, "visual", "Created a matching visual", result.get("image_prompt", "Matched the illustration to the post."), event_id=f"image:{post_id}:{payload.mode}")
            return hydrate_post(db(), updated)

    @app.post("/api/posts/{post_id}/approve")
    def approve(post_id: str):
        post = required("posts", post_id)
        if post["status"] not in {"draft", "needs_review", "approved"} or not post.get("content"):
            raise HTTPException(409, "Only completed drafts can be approved.")
        if post["status"] == "approved":
            return hydrate_post(db(), post)
        result = db().patch("posts", post_id, {"status": "approved", "approved_at": utcnow()})
        db().add_event(post_id, "human", "Approved for scheduling", "The creator reviewed and approved the content.")
        return hydrate_post(db(), result)

    @app.post("/api/posts/{post_id}/schedule")
    def schedule(post_id: str, payload: ScheduleInput):
        post = required("posts", post_id)
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
        post = required("posts", post_id)
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
        post = required("posts", post_id)
        if post["status"] not in {"published_manually", "published"}:
            raise HTTPException(409, "Only published posts can receive performance feedback.")
        if post.get("is_demo") and payload.source != "simulated":
            raise HTTPException(400, "Demonstration posts can only receive simulated feedback.")
        observation = {**payload.model_dump(), "id": f"{post_id}:{payload.source}:{payload.window}",
                       "post_id": post_id, "brand_id": post["brand_id"], "captured_at": utcnow()}
        db().put("feedback", observation)
        db().add_event(post_id, "feedback", f"Recorded {payload.window} performance", f"{payload.source} observation: {payload.impressions} impressions, {payload.comments} comments, {payload.reposts} reposts.", [observation["id"]])
        return observation

    @app.post("/api/brands/{brand_id}/learn")
    def learning(brand_id: str, payload: LearnInput):
        required("brands", brand_id)
        return learn(db(), brand_id, payload.source, payload.window)

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

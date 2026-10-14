"""Persistent named-agent graph with visible, bounded editorial refinement."""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from pydantic import model_validator

from . import prompts
from .mesh import MeshClient, MeshError
from .schemas import BrandProfile, Draft, InitialReview, RefinementReview, Revision, Strategy, VisualBrief


HOOKS = ("problem-first", "outcome-first", "question-first")
PIPELINE_VERSION = "2026-10-14.4"
_active_runs: set[str] = set()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _substantive(before: str, after: str) -> bool:
    """Reject punctuation-only changes and nearly identical returned drafts."""
    old = re.findall(r"\w+", before.lower())
    new = re.findall(r"\w+", after.lower())
    matcher = SequenceMatcher(None, old, new)
    changed = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal")
    return changed >= 8 and matcher.ratio() < 0.98


def _validate_hook_opening(content: str, hook: str) -> None:
    """Enforce the observable question/non-question boundary; semantics stay reviewed."""
    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    terminator = re.search(r'''[.!?]+["”’']?(?=\s|$)''', first_line)
    sentence = first_line[:terminator.end()] if terminator else first_line
    is_question = "?" in sentence
    if hook == "question-first" and not is_question:
        raise ValueError("The selected question-first hook requires a specific question as the first visible content sentence")
    if hook != "question-first" and is_question:
        raise ValueError(f"The selected {hook} hook must begin with a statement, not a question; rewrite the first sentence to express the selected hook")


def _review_outcome(model_review: dict, iteration: int) -> dict:
    """Preserve model judgments; send contradictory post-revision reviews to a human."""
    output = deepcopy(model_review)
    passing = all(item["score"] >= 4 for item in output["criteria"])
    consistent = (
        passing and not output["requests"] and output["approved"]
    ) or (
        not passing and bool(output["requests"]) and not output["approved"]
    )
    if iteration > 0 and not consistent:
        output["raw_model_review"] = deepcopy(model_review)
        output["requires_human_review"] = True
        output["review_inconsistency"] = (
            "The editor's scores, requests and approval disagree. The complete model review "
            "and all edit requests are preserved. A substantive revision is already saved; "
            "human review is required before approval."
        )
    output["approved"] = bool(output["approved"] and passing and not output["requests"])
    return output


def _demo_profile(samples: list[dict]) -> dict:
    texts = [str(sample["text"]).strip() for sample in samples]
    expressive = sum(text.count("!") for text in texts) >= 2 or any(
        word in " ".join(texts).lower() for word in ("imagine", "story", "plot twist", "curious")
    )
    tone = "Warm, curious, conversational" if expressive else "Calm, precise, practical"
    style = "Conversational openings, expressive imagery, short paragraphs" if expressive else "Short sentences, concrete steps, minimal hype"
    words = re.findall(r"\b[a-z]{5,}\b", " ".join(texts).lower())
    vocabulary = list(dict.fromkeys(word for word in words if word not in {"about", "there", "their", "would", "should", "which"}))[:8]
    return {
        "tone": tone,
        "style": style,
        "vocabulary": vocabulary or ["practical"],
        "avoid": ["Unsupported statistics", "Invented personal results", "Generic hype"],
        "evidence": [{"trait": "Illustrative sample evidence", "quote": text[:180]} for text in texts[:5]],
        "summary": "Illustrative demo profile derived with simple text heuristics; use live Mesh analysis for an AI-learned voice profile.",
    }


async def extract_profile(samples: list[dict], settings, mode: str = "live") -> dict:
    usable = [sample for sample in samples if isinstance(sample, dict) and len(str(sample.get("text", "")).strip()) >= 20]
    if len(usable) < 3 or len({str(sample["text"]).strip() for sample in usable}) < 3:
        raise ValueError("Provide at least three distinct writing samples of 20 or more characters.")
    if mode == "demo":
        return BrandProfile.model_validate(_demo_profile(usable)).model_dump()
    evidence_sources = set()
    normalize_space = lambda text: " ".join(str(text).split())

    class GroundedProfile(BrandProfile):
        @model_validator(mode="after")
        def grounded_quotes(self):
            evidence_sources.clear()
            for item in self.evidence:
                matches = {index for index, sample in enumerate(usable) if normalize_space(item.quote) in normalize_space(sample["text"])}
                if not matches:
                    raise ValueError("Every evidence quote must appear verbatim in the supplied samples")
                evidence_sources.update(matches)
            if len(evidence_sources) < 3:
                raise ValueError("Evidence quotes must cover at least three distinct supplied samples")
            return self

    client = MeshClient(settings)
    profile = await client.complete_json(prompts.PROFILE, _json({"samples": usable}), GroundedProfile)
    return profile.model_dump()


def _demo_topic(brief: str) -> tuple[str, str, str]:
    lower = brief.lower()
    if any(term in lower for term in ("rag", "retrieval", "hallucination")):
        return "reliable retrieval", "a retrieval result that looks relevant but misses the needed evidence", "inspect the retrieved passage before rewriting the prompt"
    if any(term in lower for term in ("safety", "responsible", "risk")):
        return "AI safety", "a plausible answer that quietly ignores a safety constraint", "write the unsafe outcome down before designing the happy path"
    if any(term in lower for term in ("evaluat", "eval", "benchmark")):
        return "useful AI evaluations", "a polished answer that passes a vague rubric", "turn one recurring failure into a concrete test case"
    if any(term in lower for term in ("agent", "automat")):
        return "reliable AI agents", "an agent repeating a failed action without checking its result", "define a stopping condition before adding another tool"
    if any(term in lower for term in ("cost", "latency", "optim")):
        return "practical AI trade-offs", "an optimization that moves a bottleneck instead of removing it", "measure one representative task before changing the model"
    topic = re.sub(r"(?i)^(write|create|draft)\s+(a\s+)?(linkedin\s+)?post\s+(about|on)\s+", "", brief).strip(" .")[:90]
    return topic or "better AI workflows", "a workflow that looks finished until someone tries a difficult case", "choose one concrete failure and write down what better would look like"


def _demo_draft(brief: str, hook: str, profile: dict, revision: bool) -> dict:
    topic, failure, action = _demo_topic(brief)
    expressive = any(word in _json(profile).lower() for word in ("playful", "warm", "conversational", "story", "energetic", "metaphor"))
    opening = {
        "problem-first": f"The hard part of {topic}: {failure}.",
        "outcome-first": f"Make {topic} easier to inspect, one concrete decision at a time.",
        "question-first": f"How would you spot {failure} before it reaches a user?",
    }[hook]
    if not revision:
        content = f"{opening}\n\nGood work starts with a clear goal. Teams need to pay attention to quality and make thoughtful choices. There are many approaches worth considering.\n\nStart small, learn from feedback, and keep improving your approach. Make sure the result is useful to the people who rely on it.\n\nWhat would you improve first?"
    elif expressive:
        content = (
            f"{opening}\n\nImagine a rehearsal with one stubborn prop: everything works until that prop moves. That is the kind of edge case worth keeping.\n\n"
            f"A small experiment: {action}.\n\n"
            "Give it three beats:\n• Describe the input that triggers the problem.\n• Write the response you would actually trust.\n• Change one thing, then replay that same input.\n\n"
            "For example, use a deliberately ambiguous request. If the system guesses, try a clarifying question and compare both responses. This is a proposed test, not a measured result.\n\n"
            "Keep the awkward example. It gives your next decision something real to stand on.\n\nWhich edge case would you put on the rehearsal stage?"
        )
    else:
        content = (
            f"{opening}\n\nStart with one test: {action}.\n\n"
            "1. Record a difficult input and the behavior you expect.\n2. Run the current workflow and save its actual response.\n3. Change one decision and rerun the same input.\n\n"
            "For example, try an ambiguous request with missing context. Compare an immediate answer with a response that first asks for clarification. Check whether either invents information. This is a proposed test, not a measured result.\n\n"
            "Keep the failure beside the improvement. A single example cannot establish reliability, but it gives the next review a concrete starting point.\n\n"
            "Repeat with a different difficult input before broadening the workflow.\n\nWhat failure would you add to your next review?"
        )
    return {"title": topic[:1].upper() + topic[1:], "content": content}


def _demo_review(iteration: int) -> dict:
    names = ["brief_fulfillment", "specificity", "clarity", "brand_fit", "factual_care"]
    scores = [3, 2, 3, 3, 4] if iteration == 0 else [4, 4, 4, 4, 4]
    reasons = (
        ["The topic is present, but the action is vague.", "‘Start small’ needs a concrete test or example.", "Replace broad advice with a short sequence.", "Generic phrasing obscures the sample voice.", "No invented measurements, but maintain that care in revision."]
        if iteration == 0 else
        ["The revision develops the requested topic into a practical exercise.", "An explicitly hypothetical ambiguous-input example makes the advice testable.", "The sequence identifies inputs, expectations, and a controlled change.", "Sentence style follows the selected demonstration profile.", "The revision labels its example and avoids claiming measured results."]
    )
    return {
        "criteria": [{"name": name, "score": score, "reason": reason} for name, score, reason in zip(names, scores, reasons)],
        "requests": ([
            {"issue": "The draft gives generic advice without a concrete exercise.", "instruction": "Replace generic improvement advice with a three-step test and one explicitly hypothetical example."},
            {"issue": "The draft does not express the selected voice clearly.", "instruction": "Rewrite the explanation using the selected profile's sentence style and vocabulary; retain the chosen hook."},
        ] if iteration == 0 else []),
        "approved": iteration > 0,
    }


async def generate_visual(post: dict, settings, mode: str = "live") -> dict:
    if mode == "demo":
        # Deliberate vector fixture, prominently labeled; never passed off as AI.
        title = html.escape((post.get("title") or "Your next idea")[:52])
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">
<rect width="1024" height="1024" fill="#f1efe8"/><circle cx="700" cy="260" r="220" fill="#cfddbe"/>
<path d="M190 700 C150 390 770 790 740 400" fill="none" stroke="#2d433a" stroke-width="9"/>
<path d="M702 433 L740 394 L778 433" fill="none" stroke="#2d433a" stroke-width="9"/>
<rect x="180" y="330" width="290" height="220" rx="20" fill="#fffdfa" stroke="#2d433a" stroke-width="3"/>
<path d="M220 385 H405 M220 425 H350 M220 465 H380" stroke="#a7b896" stroke-width="14" stroke-linecap="round"/>
<circle cx="720" cy="635" r="85" fill="#dfa575"/><path d="M680 635 L708 663 L761 603" fill="none" stroke="#2d433a" stroke-width="12"/>
<text x="80" y="825" font-family="sans-serif" font-size="31" fill="#243b31">{title}</text>
<text x="80" y="903" font-family="sans-serif" font-size="22" fill="#536252">Demo illustration · not AI-generated</text></svg>'''
        asset = Path(settings.data_dir) / "assets" / f"demo-{hashlib.sha256(svg.encode()).hexdigest()[:20]}.svg"
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_text(svg, encoding="utf-8")
        return {"image_url": f"/assets/{asset.name}", "image_prompt": "Illustrative demo: a draft becoming a reviewed idea. Not AI-generated.", "model": "demo-fixture", "source": "demo"}
    client = MeshClient(settings)
    brief = await client.complete_json(prompts.VISUAL, _json({"title": post.get("title"), "content": post.get("content")}), VisualBrief)
    image_prompt = brief.image_prompt + "\n\n" + prompts.VISUAL_CONSTRAINT
    result = await client.generate_image(image_prompt)
    result["reason"] = brief.reason
    result["usage"] = client.usage
    return result


class PipelineState(TypedDict, total=False):
    run_id: str
    iteration: int
    approved: bool
    requires_human_review: bool


async def run_pipeline(run_id: str, store, settings) -> None:
    """Execute/resume a run; every paid output and artifact has a durable key.

    The per-process guard prevents overlapping retries in this single-worker
    local application. SQLite checkpoints resume graph position; artifacts also
    protect completed operations if a process died before the next checkpoint.
    """
    if run_id in _active_runs:
        return
    run = store.get("runs", run_id)
    if not run or run.get("status") == "complete":
        return
    _active_runs.add(run_id)
    post_id = run["post_id"]
    mode = run.get("mode", "demo" if getattr(settings, "demo_mode", False) else "live")
    source = "demo" if mode == "demo" else "mesh"
    model = "demo-fixture" if mode == "demo" else getattr(settings, "chat_model", "openai/gpt-4o-mini")
    try:
        client = MeshClient(settings)
    except MeshError as error:
        store.patch("runs", run_id, {"status": "failed", "error": str(error), "updated_at": _now()})
        store.patch("posts", post_id, {"status": "needs_review"})
        _active_runs.discard(run_id)
        return
    client.usage.extend(run.get("usage", []))
    brand = store.get("brands", run["brand_id"]) or {}
    profile = run.get("profile") or brand.get("profile") or {}
    hook = run.get("selected_hook") or "problem-first"
    if hook not in HOOKS:
        hook = "problem-first"
    max_revisions = min(2, max(1, int(getattr(settings, "max_revisions", 2))))

    def refresh_run() -> dict:
        return store.get("runs", run_id) or run

    def artifact(key: str) -> dict | None:
        return refresh_run().get("artifacts", {}).get(key)

    def save_artifact(key: str, output: dict) -> dict:
        artifacts = dict(refresh_run().get("artifacts", {}))
        actual_model = client.usage[-1].get("actual_model") if client.usage and mode == "live" else model
        value = {"output": output, "created_at": _now(), "model": model, "actual_model": actual_model,
                 "source": source, "prompt_version": prompts.PROMPT_VERSION}
        artifacts[key] = value
        store.patch("runs", run_id, {"artifacts": artifacts, "usage": client.usage, "updated_at": _now()})
        return value

    def stage(name: str) -> None:
        store.patch("runs", run_id, {"stage": name, "status": "running", "updated_at": _now()})

    def event(key: str, node: str, choice: str, reason: str, evidence_ids: list | None = None) -> None:
        store.add_event(post_id, node, choice, reason, evidence_ids or [], event_id=f"{run_id}:{key}")

    def context(**extra) -> str:
        return _json({"brief": run["brief"], "voice_profile": profile, "selected_hook": hook, **extra})

    async def strategist(state: PipelineState) -> dict:
        stage("strategist")
        cached = artifact("strategist")
        if not cached:
            if mode == "demo":
                topic, _, action = _demo_topic(run["brief"])
                output = {"angle": f"Make {topic} concrete with a small, inspectable test.", "hook": hook, "audience": "Technical creators and practitioners building AI workflows", "outline": [f"Open with a {hook} framing", action, "Walk through a concrete example", "Close with a focused question"], "reason": run.get("strategy_reason") or "Initial exploration uses the selected hook; no performance advantage is claimed."}
            else:
                class SelectedStrategy(Strategy):
                    @model_validator(mode="after")
                    def enforce_policy(self):
                        if self.hook != hook:
                            raise ValueError(f"The hook must remain exactly {hook}; it is the selected learning policy")
                        return self

                output = (await client.complete_json(prompts.STRATEGIST, context(policy_reason=run.get("strategy_reason"), evidence_ids=run.get("evidence_ids", []), learning_snapshot_id=run.get("learning_snapshot_id")), SelectedStrategy)).model_dump()
            cached = save_artifact("strategist", output)
        strategy = cached["output"]
        store.patch("posts", post_id, {"strategy": strategy, "hook": hook, "source": source, "is_demo": mode == "demo", "profile_version": run.get("profile_version", brand.get("profile_version", 1)), "learning_version": run.get("learning_version")})
        event("strategist", "strategist", strategy["angle"], strategy["reason"], run.get("evidence_ids", []))
        return {"iteration": 0}

    def save_version(cached: dict, iteration: int) -> None:
        output = cached["output"]
        post = store.get("posts", post_id)
        kind = "draft" if iteration == 0 else "revision"
        version_id = f"{run_id}:version:{iteration}"
        version = {"id": version_id, "version": iteration + 1, "kind": kind, "title": output["title"], "content": output["content"], "addressed_requests": output.get("addressed_requests", []), **{key: cached[key] for key in ("created_at", "source", "model", "prompt_version")}}
        versions = [item for item in post.get("versions", []) if item.get("id") != version_id]
        versions.append(version)
        versions.sort(key=lambda item: item.get("version", 0))
        changes = {"title": output["title"], "content": output["content"], "versions": versions}
        if iteration == 0:
            changes["original_draft"] = output["content"]
        store.patch("posts", post_id, changes)

    async def writer(state: PipelineState) -> dict:
        stage("writer")
        cached = artifact("writer")
        if not cached:
            class PolicyDraft(Draft):
                @model_validator(mode="after")
                def enforce_opening_form(self):
                    _validate_hook_opening(self.content, hook)
                    return self

            output = _demo_draft(run["brief"], hook, profile, False) if mode == "demo" else (await client.complete_json(prompts.WRITER, context(strategy=artifact("strategist")["output"]), PolicyDraft, temperature=0.4)).model_dump()
            cached = save_artifact("writer", output)
        save_version(cached, 0)
        event("writer", "writer", "Original draft saved", "Draft follows the strategy and frozen brand profile. Preserved for editorial comparison.")
        return {"iteration": 0}

    async def editor(state: PipelineState) -> dict:
        iteration = state.get("iteration", 0)
        stage("editor" if iteration == 0 else f"editor_review_{iteration}")
        key = f"editor_{iteration}"
        cached = artifact(key)
        if not cached:
            draft = artifact("writer" if iteration == 0 else f"revision_{iteration}")["output"]
            previous = artifact(f"editor_{iteration - 1}") if iteration else None
            previous_draft = artifact("writer" if iteration == 1 else f"revision_{iteration - 1}") if iteration else None
            if mode == "demo":
                output = _demo_review(iteration)
            else:
                output = (await client.complete_json(prompts.EDITOR, context(draft=draft, iteration=iteration, previous_draft=previous_draft["output"] if previous_draft else None, previous_requests=previous["output"]["requests"] if previous else [], addressed_requests=draft.get("addressed_requests", [])), InitialReview if iteration == 0 else RefinementReview, temperature=0)).model_dump()
            output = _review_outcome(output, iteration)
            cached = save_artifact(key, output)
        output = cached["output"]
        post = store.get("posts", post_id)
        review_id = f"{run_id}:review:{iteration}"
        review = {"id": review_id, "iteration": iteration, **output, **{key: cached[key] for key in ("created_at", "source", "model", "prompt_version")}}
        reviews = [item for item in post.get("reviews", []) if item.get("id") != review_id] + [review]
        reviews.sort(key=lambda item: item.get("iteration", 0))
        store.patch("posts", post_id, {"reviews": reviews})
        requests = output["requests"]
        reason = " ".join(item["instruction"] for item in requests) if requests else " ".join(item["reason"] for item in output["criteria"])
        event(key, "editor", "Approved after revision" if output["approved"] else f"Revision review {iteration}: {len(requests)} edit requests", reason)
        if output.get("requires_human_review"):
            event(f"{key}:consistency", "coordinator", "Editor judgment requires human review", output["review_inconsistency"], [review_id])
        return {"approved": output["approved"], "iteration": iteration, "requires_human_review": output.get("requires_human_review", False)}

    async def revising_writer(state: PipelineState) -> dict:
        iteration = state.get("iteration", 0) + 1
        stage(f"revision_{iteration}")
        key = f"revision_{iteration}"
        cached = artifact(key)
        if not cached:
            previous = artifact("writer" if iteration == 1 else f"revision_{iteration - 1}")["output"]
            review = artifact(f"editor_{iteration - 1}")["output"]
            if mode == "demo":
                output = {**_demo_draft(run["brief"], hook, profile, True), "addressed_requests": ["Replaced broad advice with a three-step test and explicitly hypothetical example.", "Applied the selected voice profile to the explanation and retained the chosen hook."]}
            else:
                class SubstantiveRevision(Revision):
                    @model_validator(mode="after")
                    def content_has_changed(self):
                        if not _substantive(previous["content"], self.content):
                            raise ValueError("Revise the actual content substantively; punctuation or title-only changes do not address the editor")
                        _validate_hook_opening(self.content, hook)
                        return self

                output = (await client.complete_json(prompts.REVISION, context(strategy=artifact("strategist")["output"], draft=previous, editor_review=review), SubstantiveRevision, temperature=0.25)).model_dump()
            if not _substantive(previous["content"], output["content"]):
                raise MeshError("The writer returned only cosmetic edits. The original draft is saved; retry the revision step.")
            cached = save_artifact(key, output)
        save_version(cached, iteration)
        event(key, "writer", f"Substantive revision {iteration} saved", " ".join(cached["output"].get("addressed_requests", [])), [f"{run_id}:review:{iteration - 1}"])
        return {"iteration": iteration, "approved": False}

    async def visual(state: PipelineState) -> dict:
        if not run.get("generate_image", False):
            return {}
        stage("visual")
        cached = artifact("visual")
        if not cached:
            output = await generate_visual(store.get("posts", post_id), settings, mode)
            cached = save_artifact("visual", output)
        image_output = cached["output"]
        store.patch("posts", post_id, {"image_url": image_output["image_url"], "image_prompt": image_output["image_prompt"], "image_model": image_output["model"], "image_source": image_output["source"]})
        event("visual", "visual", "Matching visual saved", cached["output"].get("reason", cached["output"]["image_prompt"]))
        return {}

    async def finish(state: PipelineState) -> dict:
        status = "draft" if state.get("approved") else "needs_review"
        store.patch("posts", post_id, {"status": status, "updated_at": _now()})
        store.patch("runs", run_id, {"status": "complete", "stage": "complete", "completed_at": _now(), "updated_at": _now(), "error": None})
        reason = "The final editor review approved all criteria." if status == "draft" else "The bounded editor loop ended with unresolved issues; review before approval."
        if state.get("requires_human_review"):
            reason = "The editor's scores, requests and approval disagree. Its full review is retained for human judgment; no automatic approval was issued."
        event("finish", "coordinator", "Content ready for human review" if status == "draft" else "Human review required", "At least one substantive revision was saved. " + reason)
        return {}

    def next_after_editor(state: PipelineState) -> str:
        if state.get("iteration", 0) == 0:
            return "revising_writer"
        if state.get("requires_human_review"):
            return "visual"
        if not state.get("approved") and state["iteration"] < max_revisions:
            return "revising_writer"
        return "visual"

    builder = StateGraph(PipelineState)
    for name, node in (("strategist", strategist), ("writer", writer), ("editor", editor), ("revising_writer", revising_writer), ("visual", visual), ("finish", finish)):
        builder.add_node(name, node)
    builder.add_edge(START, "strategist")
    builder.add_edge("strategist", "writer")
    builder.add_edge("writer", "editor")
    builder.add_conditional_edges("editor", next_after_editor, {"revising_writer": "revising_writer", "visual": "visual"})
    builder.add_edge("revising_writer", "editor")
    builder.add_edge("visual", "finish")
    builder.add_edge("finish", END)

    try:
        Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
        store.patch("runs", run_id, {"status": "running", "error": None, "error_diagnostics": None, "pipeline_version": PIPELINE_VERSION, "updated_at": _now()})
        async with AsyncSqliteSaver.from_conn_string(str(Path(settings.data_dir) / "checkpoints.sqlite")) as saver:
            graph = builder.compile(checkpointer=saver)
            config = {"configurable": {"thread_id": run_id}, "recursion_limit": 20}
            checkpoint = await graph.aget_state(config)
            await graph.ainvoke(None if checkpoint.next else {"run_id": run_id, "iteration": 0}, config=config)
    except asyncio.CancelledError:
        store.patch("runs", run_id, {"status": "interrupted", "error": "Run interrupted. Completed steps are saved and can be resumed.", "updated_at": _now()})
        raise
    except Exception as error:
        message = str(error) if isinstance(error, MeshError) else "This run stopped unexpectedly. Completed steps are saved; retry to resume."
        diagnostics = error.diagnostics if isinstance(error, MeshError) else None
        store.patch("runs", run_id, {"status": "failed", "error": message, "error_diagnostics": diagnostics, "usage": client.usage, "updated_at": _now()})
        store.patch("posts", post_id, {"status": "needs_review"})
        event("failure", "coordinator", "Run paused at a recoverable failure", message)
    finally:
        _active_runs.discard(run_id)

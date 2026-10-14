"""Authored demonstration fixtures. These are not real creators or engagement."""
from datetime import datetime, timedelta, timezone

from .learning import HOOKS, build_snapshot
from .store import utcnow

ADA_SAMPLES = [
    "An AI evaluation starts with a failure you can name. Pick one task. Save the input. Write down what a good answer must contain. Then test the same input after every change. A small, repeatable check is more useful than an impressive screenshot. What would you test first?",
    "Retrieval is a filtering problem before it is a writing problem. If the right document never reaches the model, a better prompt cannot cite it. Inspect the retrieved passages first. Then inspect the answer. Keep those two measurements separate.",
    "Start with one tool and one success condition. Give your agent a narrow job, a time limit, and a way to stop. Add the next tool only when a real example needs it. Complexity should earn its place.",
    "A useful AI safety check has a concrete failure case. Save the input that broke your boundary. Add it to the test set. Run it when the prompt changes. Safety gets easier to discuss when we can point at behavior.",
    "Treat a prompt change like a code change. Name the behavior you expect. Compare before and after on the same examples. Keep the failures in your report. The point is to learn where the system is dependable, not to collect good-looking answers.",
]
MILO_SAMPLES = [
    "What if the first version is supposed to be small? When I think about building with AI, I picture a notebook before a control room. One question. One little experiment. Enough room to notice what surprises us. What are you curious about this week?",
    "There is something comforting about a test you can understand. An input, an answer, and a quiet moment to ask: is that what we meant? We do not have to solve every edge case today. We can start by looking closely at one.",
    "Maybe the most useful feature is a pause button. A moment for a person to look at the draft, ask a question, and steer. I like tools that leave room for that conversation. What would make an AI tool feel more like a collaborator to you?",
    "A pile of documents is not the same as an answer. I think of retrieval as finding the right page in a very messy notebook. The writing can come later. First, can we find the thing we actually need?",
    "Good feedback gives the next attempt somewhere to go. 'Make it better' is a foggy map. 'Show me one concrete example' is a path. Small directions can change the whole conversation. What is the most helpful feedback you have received?",
]

DEMO_COVER = '''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675">
<rect width="1200" height="675" fill="#e9eee8"/><g fill="none" stroke="#bccbc0" stroke-width="1"><circle cx="850" cy="340" r="245"/><circle cx="850" cy="340" r="185"/><circle cx="850" cy="340" r="125"/></g>
<path d="M830 205L875 320L990 365L875 410L830 525L785 410L670 365L785 320Z" fill="#24614c"/>
<rect x="80" y="80" width="115" height="30" rx="15" fill="#d2ded1"/><text x="96" y="101" font-family="Arial,sans-serif" font-size="14" fill="#315541">FIELD NOTES</text>
<text x="80" y="245" font-family="Georgia,serif" font-size="67" fill="#1e352a">Small tests.</text><text x="80" y="324" font-family="Georgia,serif" font-size="67" fill="#1e352a">Better agents.</text>
<text x="82" y="393" font-family="Arial,sans-serif" font-size="23" fill="#587163">Give every change a test it can fail.</text>
<text x="80" y="600" font-family="Arial,sans-serif" font-size="16" fill="#587163">CreatorOS · Demo illustration · Not AI-generated</text></svg>'''


def seed_demo(store):
    if store.get("meta", "demo-seed-v1"):
        return
    now = datetime.now(timezone.utc)
    definitions = [
        ("brand-ada", "Ada Chen", "Practical AI engineering, explained clearly.", ADA_SAMPLES,
         "Calm, precise, encouraging", "Short sentences. Concrete examples. Direct, practical advice.",
         ["concrete", "test", "inspect", "repeatable"], "A precise technical educator who turns complicated systems into small, testable actions."),
        ("brand-milo", "Milo Parker", "Curiosity, craft, and building things with AI.", MILO_SAMPLES,
         "Warm, curious, conversational", "Gentle questions. Simple analogies. Reflective pacing.",
         ["curious", "small", "conversation", "notice"], "A conversational builder who uses gentle questions and everyday analogies to explore technical ideas."),
    ]
    for bid, name, description, samples, tone, style, vocabulary, summary in definitions:
        store.put("brands", {
            "id": bid, "name": name, "description": description, "is_demo": True,
            "samples": [{"text": t, "source": "Authored demonstration sample — fictional creator"} for t in samples],
            "profile": {"tone": tone, "style": style, "vocabulary": vocabulary,
                        "avoid": ["Unsupported statistics", "Invented experience", "Hype and empty promises"],
                        "evidence": [{"trait": "Concrete, approachable language", "quote": samples[0].split(". ")[0] + "."}],
                        "summary": summary},
            "profile_version": 1, "profile_source": "demo", "created_at": utcnow(),
        })
    topics = [
        ("A retrieval failure is not a writing failure", "A better prompt cannot cite a document the retriever never found. Inspect the retrieved passages before tuning the answer. Save one example where retrieval fails, then compare it after the next change."),
        ("Your agent needs a stopping rule", "An agent with too many tools has more ways to get lost. Start with one tool, one success condition, and a clear stopping rule. Add complexity only when a test shows why it is needed."),
        ("Make prompt changes easier to trust", "Make your next prompt change easier to evaluate: keep the inputs fixed. Write down the expected behavior before generating. Compare the results side by side and keep the failures in the report."),
        ("Turn feedback into a useful next step", "Get more useful revisions by naming one thing to change. Ask for a concrete example, a clearer opening, or a supported claim. Specific feedback gives the next draft a direction."),
        ("What does a good answer need to contain?", "What does a good answer need to contain? Before testing an AI workflow, write three observable checks. Run them against the same inputs. Look at what fails before adding another feature."),
        ("Can you explain why your agent stopped?", "Can you explain why your agent stopped? Log the tool result, the next decision, and the reason for ending the run. A useful trace lets another person understand the outcome without guessing."),
    ]
    metrics = [(1800, 12, 4), (2200, 14, 6), (2100, 39, 13), (1900, 35, 11), (1700, 19, 6), (2300, 23, 8)]
    for idx, ((title, content), (impressions, comments, reposts)) in enumerate(zip(topics, metrics)):
        pid = f"demo-history-{idx + 1}"
        published = (now - timedelta(days=idx + 2)).isoformat()
        store.put("posts", {
            "id": pid, "brand_id": "brand-ada", "brief": title, "title": title,
            "content": content, "original_draft": content, "status": "published_manually",
            "hook": HOOKS[idx // 2], "source": "simulated", "is_demo": True,
            "created_at": published, "published_at": published, "scheduled_at": None,
            "image_url": None, "run_id": None, "profile_version": 1, "learning_version": 0,
            "versions": [{"version": 1, "content": content, "kind": "imported_demo"}], "reviews": [],
        })
        store.put("feedback", {
            "id": f"{pid}:simulated:24h", "post_id": pid, "brand_id": "brand-ada",
            "source": "simulated", "window": "24h", "impressions": impressions,
            "reactions": comments * 3, "comments": comments, "reposts": reposts,
            "captured_at": (now - timedelta(days=idx + 1)).isoformat(),
        })
    snapshot = build_snapshot(store.list("posts"), store.list("feedback"), "brand-ada", "simulated", "24h", 1)
    store.put("snapshots", snapshot)
    original = "AI agents are changing the way we build software. It is important to evaluate them carefully. You should test your agents, track their performance, and improve them over time. With the right approach, we can build better AI systems. What do you think?"
    content = "Make your next agent change easier to trust.\n\nGive it a test it can fail.\n\nBefore adding another tool, write down one task and three things a good result must contain. Then run that same task before and after the change.\n\nStart small:\n→ Keep the input fixed.\n→ Check the tool result, not just the final answer.\n→ Save the failure alongside the success.\n\nIf the change fixes one case but breaks another, that is useful evidence. Keep both in the report.\n\nA small, repeatable evaluation tells you more than a polished screenshot.\n\nWhat is the first failure case you would put in your test set?"
    store.put("posts", {
        "id": "demo-showcase", "brand_id": "brand-ada", "brief": "A LinkedIn post about why small, repeatable evaluations make AI agents more dependable.",
        "title": "Give every agent change a test it can fail", "content": content,
        "original_draft": original, "status": "draft", "hook": "outcome-first",
        "source": "simulated", "is_demo": True, "created_at": utcnow(),
        "scheduled_at": None, "published_at": None, "image_url": "/assets/demo-cover.svg",
        "image_source": "demo", "run_id": "demo-run", "profile_version": 1,
        "learning_version": 1, "learning_snapshot_id": snapshot["id"],
        "strategy": {"angle": "Treat each agent change as a small, repeatable experiment", "hook": "outcome-first", "audience": "Engineers building AI agents", "outline": ["Start with the outcome", "Give a three-step method", "Ask for one failure case"], "reason": snapshot["explanation"]},
        "versions": [{"version": 1, "content": original, "kind": "initial"}, {"version": 2, "content": content, "kind": "revision"}],
        "reviews": [{"criteria": [{"name": "Specificity", "score": 2, "reason": "Illustrative critique: the initial draft gives generic advice without an actionable example."}, {"name": "Brand fit", "score": 3, "reason": "Illustrative critique: replace broad claims with concrete steps."}],
                     "requests": [{"issue": "Generic opening", "instruction": "Lead with the benefit of repeatable testing."}, {"issue": "No concrete method", "instruction": "Add three observable steps the reader can try."}, {"issue": "Vague closing question", "instruction": "Ask the reader for their first failure case."}], "approved": True, "source": "demo"}],
    })
    for node, choice, reason in [
        ("strategist", "Lead with an outcome", "Illustrative run: outcome-first openings have the highest rate in the simulated feedback dataset."),
        ("editor", "Replace generic advice with a repeatable test", "The draft needs concrete actions and a question that invites a specific answer."),
        ("writer", "Added a three-step evaluation method", "Addressed the critique with fixed inputs, tool-result checks, and a retained failure case."),
        ("visual", "Small tests. Better agents.", "Authored demo illustration. Live image generation is available through Mesh."),
    ]:
        store.add_event("demo-showcase", node, choice, reason, snapshot["evidence_ids"] if node == "strategist" else [], event_id=f"demo:{node}")
    store.put("runs", {"id": "demo-run", "post_id": "demo-showcase", "brand_id": "brand-ada", "mode": "demo", "status": "complete", "stage": "complete", "error": None, "created_at": utcnow()})
    (store.data_dir / "assets" / "demo-cover.svg").write_text(DEMO_COVER)
    store.put("meta", {"id": "demo-seed-v1", "created_at": utcnow(), "description": "All seeded creators, posts, feedback, and illustrations are authored demonstration fixtures."})

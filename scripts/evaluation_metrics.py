"""Deterministic, descriptive benchmark metrics; never audience-uplift estimates."""
from __future__ import annotations

import random
import re
import statistics


def constraint_checks(text: str, constraints: dict | None = None) -> dict:
    constraints = constraints or {}
    words = len(text.split())
    hashtags = re.findall(r"(?<!\w)#[\w]+", text)
    bullets = re.findall(r"(?m)^\s*(?:[-*•→]|\d+[.)])\s+", text)
    checks = {}
    for key, actual, direction in (
        ("min_words", words, "min"), ("max_words", words, "max"),
        ("max_characters", len(text), "max"), ("max_hashtags", len(hashtags), "max"),
        ("min_bullets", len(bullets), "min"), ("max_bullets", len(bullets), "max"),
    ):
        if key in constraints:
            checks[key] = actual >= constraints[key] if direction == "min" else actual <= constraints[key]
    if constraints.get("plain_text"):
        checks["plain_text"] = not bool(re.search(r"```|\*\*|(?m:^#{1,6}\s)", text))
    return {"words": words, "characters": len(text), "hashtags": len(hashtags),
            "bullets": len(bullets), "checks": checks,
            "passed": all(checks.values()) if checks else None,
            "scope": "Only explicit, machine-checkable constraints; not factual verification."}


def paired_bootstrap(values: list[float], *, seed: int = 2026, samples: int = 2000) -> dict:
    """Resample paired differences, preserving each before/after pair."""
    if not values:
        return {"n": 0, "mean_delta": None, "interval_95": None, "small_n": True}
    rng = random.Random(seed)
    means = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(samples))
    return {"n": len(values), "mean_delta": round(statistics.mean(values), 4),
            "interval_95": [round(means[int((samples - 1) * p)], 4) for p in (0.025, 0.975)],
            "small_n": len(values) < 30, "seed": seed, "resamples": samples,
            "method": "Percentile paired bootstrap of score differences; descriptive synthetic-case uncertainty only. Repeated topics and shared judges may be correlated."}

"""Explicit, deterministic brief contracts. Suggestions always require confirmation.

These checks inspect body text, including headings and bullets, but never the
internal title. They do not assess meaning, factual accuracy, or all prose rules.
"""
from __future__ import annotations

import hashlib
import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Bound = Annotated[int, Field(strict=True, ge=0, le=10000)]
SmallBound = Annotated[int, Field(strict=True, ge=0, le=100)]
CONTRACT_VERSION = "brief-contract-v1"
BULLETS = re.compile(r"(?m)^[ \t]*(?:[-*•→]|\d+[.)])[ \t]+")
HASHTAGS = re.compile(r"(?<!\w)#[\w]+")
MARKDOWN = re.compile(
    r"\*\*[^*\n]+\*\*|__[^_\n]+__|```|`[^`\n]+`|"
    r"!?\[[^\]\n]+\]\([^)]+\)|(?m:^[ \t]{0,3}#{1,6}[ \t])|"
    r"(?m:^[ \t]*>[ \t])|(?<!\*)\*[^*\n]+\*(?!\*)|"
    r"(?<!\w)_[^_\n]+_(?!\w)|</?[A-Za-z][^>\n]*>"
)


def _heading(value: str) -> str:
    return " ".join(value.strip().rstrip(":").split()).casefold()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_words: Bound | None = None
    max_words: Bound | None = None
    max_characters: Bound | None = None
    min_bullets: SmallBound | None = None
    max_bullets: SmallBound | None = None
    max_hashtags: SmallBound | None = None
    required_sections: list[Annotated[str, Field(strict=True, min_length=1, max_length=80)]] = Field(default_factory=list, max_length=12)
    plain_text: bool = Field(default=False, strict=True)

    @field_validator("required_sections")
    @classmethod
    def clean_sections(cls, values: list[str]) -> list[str]:
        cleaned = []
        for value in values:
            if any(character in value for character in ("\n", "\r", "\t")) or not value.strip():
                raise ValueError("Each required section must be a nonempty heading on one line.")
            heading = " ".join(value.split()).rstrip(":").strip()
            if not heading or re.search(r"[#*`]|</?\w", heading):
                raise ValueError("Required sections must be plain-text heading names without markup.")
            if _heading(heading) in {_heading(item) for item in cleaned}:
                raise ValueError("Required section names must be distinct.")
            cleaned.append(heading)
        return cleaned

    @model_validator(mode="after")
    def coherent_ranges(self):
        for name in ("words", "bullets"):
            minimum, maximum = getattr(self, f"min_{name}"), getattr(self, f"max_{name}")
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError(f"Minimum {name} cannot exceed maximum {name}.")
        if self.max_words is not None and self.max_words < sum(len(section.split()) for section in self.required_sections):
            raise ValueError("Maximum words cannot fit the required section headings.")
        if self.min_bullets and self.max_words is not None and self.max_words < self.min_bullets * 2:
            raise ValueError("Maximum words cannot fit the required bullets (markers count as words).")
        return self


def validate_contract(contract: dict | Contract | None, platform: str = "linkedin") -> dict:
    """Return a canonical, bounded contract or raise ValueError for contradictions."""
    if platform not in {"linkedin", "newsletter"}:
        raise ValueError("Choose LinkedIn or newsletter.")
    value = contract if isinstance(contract, Contract) else Contract.model_validate({} if contract is None else contract)
    ceiling = 3000 if platform == "linkedin" else 10000
    if value.max_characters is not None and not 100 <= value.max_characters <= ceiling:
        raise ValueError(f"Maximum characters must be between 100 and {ceiling} for {platform}.")
    effective_min_words = max(value.min_words or 0, 400 if platform == "newsletter" else 1)
    effective_max_words = value.max_words if value.max_words is not None else (700 if platform == "newsletter" else ceiling)
    if platform == "newsletter" and (effective_min_words > 700 or effective_max_words < 400 or effective_max_words > 700):
        raise ValueError("Newsletter word constraints must fit its 400–700 word acceptance range.")
    if effective_max_words < effective_min_words:
        raise ValueError("The word range cannot fit the selected platform.")
    character_limit = value.max_characters or ceiling
    if effective_min_words * 2 - 1 > character_limit:
        raise ValueError("Minimum words cannot fit the character limit, even with one-letter words.")
    section_characters = sum(len(section) for section in value.required_sections) + max(0, len(value.required_sections) - 1)
    if section_characters > character_limit:
        raise ValueError("Required section headings cannot fit the character limit.")
    return value.model_dump(exclude_none=True)


def check_contract(content: str, contract: dict | Contract | None) -> dict:
    """Check explicit constraints only; an empty contract is unassessed, not passed."""
    value = contract if isinstance(contract, Contract) else Contract.model_validate({} if contract is None else contract)
    counts = {"words": len(content.split()), "characters": len(content),
              "bullets": len(BULLETS.findall(content)), "hashtags": len(HASHTAGS.findall(content))}
    checks = []
    for key, metric, direction in (
        ("min_words", "words", "min"), ("max_words", "words", "max"),
        ("max_characters", "characters", "max"), ("min_bullets", "bullets", "min"),
        ("max_bullets", "bullets", "max"), ("max_hashtags", "hashtags", "max"),
    ):
        bound = getattr(value, key)
        if bound is not None:
            passed = counts[metric] >= bound if direction == "min" else counts[metric] <= bound
            checks.append({"key": key, "label": f"{'Minimum' if direction == 'min' else 'Maximum'} {metric}",
                           "expected": bound, "actual": counts[metric], "passed": passed})
    headings = {_heading(line) for line in content.splitlines() if line.strip()}
    for index, section in enumerate(value.required_sections):
        present = _heading(section) in headings
        checks.append({"key": f"required_section:{index}", "label": f"Required section: {section}",
                       "expected": section, "actual": "present" if present else "missing", "passed": present})
    if value.plain_text:
        formatted = bool(MARKDOWN.search(content))
        checks.append({"key": "plain_text", "label": "Plain text", "expected": "No detected Markdown or HTML formatting",
                       "actual": "formatting detected" if formatted else "plain text", "passed": not formatted})
    violations = [f"{item['label']}: expected {item['expected']}; actual {item['actual']}." for item in checks if not item["passed"]]
    return {"version": CONTRACT_VERSION, "passed": all(item["passed"] for item in checks) if checks else None,
            "checks": checks, "violations": violations, "counts": counts,
            "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
            "scope": "Body text including headings; whitespace-separated words; line-start bullet markers. Required sections match whole lines, ignoring case, repeated whitespace and a trailing colon. Formatting checks detect common Markdown and HTML. No factual or semantic verification."}


def suggest_contract(brief: str, platform: str = "linkedin") -> dict:
    """Conservatively recognize simple numeric rules, without paid calls or inference."""
    if not isinstance(brief, str) or len(brief) > 10000:
        raise ValueError("Provide a brief of at most 10000 characters.")
    validate_contract({}, platform)
    values: dict[str, list[int]] = {}
    warnings = ["Suggestions recognize only simple explicit numeric rules. Review and confirm them; other instructions, meaning and factual accuracy are not checked."]
    text = brief.casefold()

    def record(key: str, number: str | int) -> None:
        # Extremely long integer strings can exceed Python's conversion limit;
        # retain an out-of-range sentinel so the suggestion is rejected safely.
        numeric = 10001 if isinstance(number, str) and len(number) > 6 else int(number)
        values.setdefault(key, []).append(numeric)

    # Ranges and bounded statements are intentionally narrower than general prose.
    covered = []
    for match in re.finditer(r"\b(\d+)\s*(?:[-–—]|to)\s*(\d+)\s*(words?|bullets?)\b", text):
        metric = "words" if match[3].startswith("word") else "bullets"
        record(f"min_{metric}", match[1])
        record(f"max_{metric}", match[2])
        covered.append(match.span())
    units = r"words?|characters?|bullets?|hashtags?"
    for match in re.finditer(rf"\b(at least|no fewer than|not fewer than|no less than|not less than|minimum(?: of)?|min\.?|at most|up to|no more than|not more than|maximum(?: of)?|max\.?|under|fewer than|less than|exactly)\s+(\d+)\s*({units})\b", text):
        prefix, number, raw = match.groups()
        if re.search(r"\b(?:not|never|avoid)(?:\s+(?:use|write|include))?\s*$", text[max(0, match.start() - 30):match.start()]):
            warnings.append("A negated numeric rule needs manual interpretation and was not suggested.")
            covered.append(match.span())
            continue
        metric = next(name for name in ("words", "characters", "bullets", "hashtags") if raw.rstrip("s") == name.rstrip("s"))
        minimum = prefix in {"at least", "no fewer than", "not fewer than", "no less than", "not less than", "minimum", "minimum of", "min", "min."}
        if minimum and metric in {"characters", "hashtags"}:
            warnings.append(f"Minimum {metric} is not supported; this instruction needs manual review.")
        elif prefix == "exactly":
            if metric in {"words", "bullets"}:
                record(f"min_{metric}", number)
                record(f"max_{metric}", number)
            else:
                warnings.append(f"Exact {metric} is not supported; this instruction needs manual review.")
        else:
            adjusted = (10001 if len(number) > 6 else int(number)) - (1 if prefix in {"under", "fewer than", "less than"} else 0)
            record(f"{'min' if minimum else 'max'}_{metric}", adjusted)
        covered.append(match.span())
    for match in re.finditer(r"\b(no|without|zero)\s+(bullets?|hashtags?)\b", text):
        record("max_bullets" if match[2].startswith("bullet") else "max_hashtags", 0)
        covered.append(match.span())
    proposal: dict = {}
    ambiguous = False
    for key, candidates in values.items():
        if len(set(candidates)) > 1:
            ambiguous = True
            warnings.append(f"Multiple different {key.replace('_', ' ')} instructions were found. Choose the intended rule explicitly.")
        else:
            proposal[key] = candidates[0]
    if re.search(r"\bplain[- ]text\b|\bno markdown\b|\bwithout markdown\b", text):
        proposal["plain_text"] = True
    remaining = "".join(character if not any(start <= index < end for start, end in covered) else " " for index, character in enumerate(text))
    if re.search(r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:words?|characters?|bullets?|hashtags?)\b|\b(?:around|about|approximately|sections?|headings?)\b", remaining):
        warnings.append("Some quantity or section instructions are ambiguous or unsupported. Enter their intended bounds or exact section names yourself.")
    if ambiguous:
        return {"contract": Contract().model_dump(exclude_none=True), "warnings": warnings + ["No suggested rules were applied because numeric instructions conflict."]}
    try:
        canonical = validate_contract(proposal, platform)
    except ValueError as error:
        return {"contract": Contract().model_dump(exclude_none=True), "warnings": warnings + [f"These suggested rules conflict or exceed supported/platform limits: {error}. Enter a compatible contract explicitly."]}
    return {"contract": canonical, "warnings": warnings}

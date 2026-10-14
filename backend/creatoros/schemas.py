"""Validated outputs shared by the independently prompted CreatorOS agents."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Hook = Literal["problem-first", "outcome-first", "question-first"]
Platform = Literal["linkedin", "newsletter"]


class AgentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class VoiceEvidence(AgentOutput):
    trait: str = Field(min_length=3, max_length=240)
    quote: str = Field(min_length=5, max_length=350)


class BrandProfile(AgentOutput):
    tone: str = Field(min_length=3, max_length=500)
    style: str = Field(min_length=3, max_length=800)
    vocabulary: list[str] = Field(min_length=1, max_length=15)
    avoid: list[str] = Field(min_length=1, max_length=12)
    evidence: list[VoiceEvidence] = Field(min_length=3, max_length=8)
    summary: str = Field(min_length=10, max_length=1000)


class Strategy(AgentOutput):
    angle: str = Field(min_length=10, max_length=600)
    hook: Hook
    audience: str = Field(min_length=3, max_length=300)
    outline: list[str] = Field(min_length=3, max_length=6)
    reason: str = Field(min_length=10, max_length=800, description="Concise, observable explanation of the strategy: target 200–400 characters, hard maximum 800 characters. Summarize the brief, audience and selected policy without repeating the outline or full voice profile.")

    @field_validator("reason", mode="before")
    @classmethod
    def strategy_reason_length_feedback(cls, reason):
        if isinstance(reason, str) and len(reason.strip()) > 800:
            size = len(reason.strip())
            raise ValueError(f"Strategy reason currently contains {size} characters; maximum 800. Remove at least {size - 800} characters and target 200–400 characters. State the essential observable reason without repeating the outline or voice profile")
        return reason


class Draft(AgentOutput):
    title: str = Field(min_length=3, max_length=160)
    content: str = Field(min_length=100, max_length=3000)

    @field_validator("content")
    @classmethod
    def linkedin_plain_text(cls, content: str) -> str:
        markdown = r"\*\*[^*\n]+\*\*|__[^_\n]+__|```|`[^`\n]+`|!?\[[^\]\n]+\]\([^)]+\)|(?m:^\s{0,3}#{1,6}\s)"
        if re.search(markdown, content):
            raise ValueError("LinkedIn content must be plain text: remove Markdown bold, headings, code formatting and Markdown links; plain bullets, emojis and bare URLs are allowed")
        return content


class Revision(Draft):
    addressed_requests: list[str] = Field(min_length=1, max_length=8)


class NewsletterDraft(Draft):
    """A different format, with an email subject and developed plain-text sections."""
    title: str = Field(min_length=3, max_length=100)
    content: str = Field(min_length=100, max_length=10000, description="Plain-text newsletter body: target 500–550 words, strictly 400–700 words including headings. Use a concise opening, four useful sections, one worked hypothetical example, a checklist, limitations, and one closing action.")

    @field_validator("content")
    @classmethod
    def newsletter_structure(cls, content: str) -> str:
        words = len(content.split())
        if not 400 <= words <= 700:
            adjustment = f"Remove at least {words - 700} words; shorten existing sections instead of adding paragraphs" if words > 700 else f"Add at least {400 - words} words of useful explanation"
            raise ValueError(f"Newsletter body currently contains {words} words; it must contain 400–700 words. {adjustment}. Target 500–550 words while retaining the worked example, exercise and trade-offs")
        blocks = re.split(r"\n\s*\n", content.strip())
        headings = [block for block in blocks[1:] if "\n" not in block and 3 <= len(block) <= 80 and not block.endswith((".", "?", "!"))]
        if len(headings) < 3:
            raise ValueError("Newsletter requires at least three descriptive plain-text section headings, each separated from paragraphs by blank lines")
        return content


class NewsletterRevision(NewsletterDraft):
    addressed_requests: list[str] = Field(min_length=1, max_length=8)


class Criterion(AgentOutput):
    name: Literal["brief_fulfillment", "specificity", "clarity", "brand_fit", "factual_care"]
    score: int = Field(ge=1, le=5)
    reason: str = Field(min_length=5, max_length=1200)


class EditRequest(AgentOutput):
    issue: str = Field(min_length=5, max_length=400)
    instruction: str = Field(min_length=10, max_length=700)


class Review(AgentOutput):
    criteria: list[Criterion] = Field(min_length=5, max_length=5)
    requests: list[EditRequest] = Field(max_length=6)
    approved: bool

    @field_validator("criteria")
    @classmethod
    def unique_criteria(cls, criteria: list[Criterion]) -> list[Criterion]:
        if len({item.name for item in criteria}) != 5:
            raise ValueError("Score each of the five distinct criteria exactly once")
        return criteria


class InitialReview(Review):
    requests: list[EditRequest] = Field(min_length=1, max_length=6)


class RefinementReview(Review):
    """Validate structure; judgment inconsistencies go to a human, not retries.

    A model can legitimately produce parseable criticism with inconsistent
    scores. The coordinator retains it and stops safely for human review.
    """


class VisualBrief(AgentOutput):
    image_prompt: str = Field(min_length=50, max_length=2000, description="Concise image-generation prompt: target 500–1000 characters; hard maximum 2000 characters. Describe one scene, composition, palette and focal point without repeating constraints. No readable text or labeled objects.")
    reason: str = Field(min_length=10, max_length=1200)

    @field_validator("image_prompt", mode="before")
    @classmethod
    def image_prompt_length_feedback(cls, prompt):
        if isinstance(prompt, str) and len(prompt.strip()) > 2000:
            size = len(prompt.strip())
            raise ValueError(f"Image prompt currently contains {size} characters; maximum 2000. Remove at least {size - 2000} characters and target 500–1000 characters. Shorten the existing scene description instead of adding instructions")
        return prompt

    @field_validator("image_prompt")
    @classmethod
    def prohibit_literal_text_instructions(cls, prompt: str) -> str:
        # Labels made only of icons are visual organization, not typography.
        # Remove that explicit safe construction before looking for instructions
        # that put readable words onto documents, screens, or other objects.
        icon_only = r"\blabel(?:ed|led)\s+(?:only\s+)?(?:by|with|using)\s+(?:simple\s+)?(?:icons?|symbols?|shapes?)(?:\s+only)?(?:\s*\(no\s+text\))?"
        checked = re.sub(icon_only, "", prompt, flags=re.IGNORECASE)
        literal_text = r'''\b(?:label(?:ed|led)|captioned|inscribed|spelling)\b|\b(?:text|words?|letters?|title|caption|label)\s+(?:reading|saying|that\s+(?:reads|says)|of)\b|\b(?:text|words?|letters?|title|caption|label)\s*(?:[:=]\s*)?["“‘']'''
        if re.search(literal_text, checked, re.IGNORECASE):
            raise ValueError("The image must contain no readable text. Remove instructions for labeled objects, captions, inscriptions or quoted words; communicate the idea with unmarked shapes instead.")
        return prompt

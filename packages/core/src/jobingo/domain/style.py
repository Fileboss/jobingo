"""The user's writing style: a register, reference sentences for the tone, and turns
of phrase the model must never use. The forbidden list is enforced in code, after the
call, on every rewrite."""

import re

from pydantic import BaseModel

from jobingo.domain.frontmatter import lenient_front_matter
from jobingo.domain.text import fold

_HEADING_RE = re.compile(r"^#{2,3}\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
# Matched on the folded heading: "Tournures interdites" and "tournures interdites" alike.
_FORBIDDEN_HEADINGS = ("interdit", "banni", "proscrit")
_EXAMPLE_HEADINGS = ("reference", "exemple", "phrase")


class StyleGuide(BaseModel):
    tone_register: str = ""
    examples: list[str] = []
    forbidden: list[str] = []


def parse_style(text: str) -> StyleGuide:
    """A Markdown style sheet: a `registre` in the front matter, then bullet lists
    under headings naming reference sentences or forbidden turns of phrase."""
    metadata, body, _ = lenient_front_matter(text)
    guide = StyleGuide(tone_register=str(metadata.get("registre", "")))
    bucket: list[str] | None = None
    for raw_line in body.splitlines():
        line = raw_line.strip()
        heading = _HEADING_RE.match(line)
        if heading:
            folded = fold(heading.group(1))
            if any(word in folded for word in _FORBIDDEN_HEADINGS):
                bucket = guide.forbidden
            elif any(word in folded for word in _EXAMPLE_HEADINGS):
                bucket = guide.examples
            else:
                bucket = None
            continue
        bullet = _BULLET_RE.match(line)
        if bullet and bucket is not None:
            bucket.append(bullet.group(1).strip())
    return guide


def forbidden_hits(text: str, forbidden: list[str]) -> list[str]:
    """The forbidden turns of phrase found in `text`, whatever their case or accents."""
    folded = fold(text)
    return [phrase for phrase in forbidden if phrase.strip() and fold(phrase) in folded]

"""Render a cover letter. Identity reaches this module as a parameter, at render time,
and never through the draft, so it cannot have reached the model."""

import re
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from jobingo.domain.identity import Identity
from jobingo.domain.letter import LetterManifest
from jobingo.render.pdf import render_pdf

LETTER_DIR = Path(__file__).parent / "templates" / "lettre-classique"

# Month names rather than a locale: the locale is process-wide and depends on the host.
_MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


@dataclass(frozen=True)
class RenderedLetter:
    pdf: bytes
    pages: int


@cache
def load_letter_manifest() -> LetterManifest:
    data = yaml.safe_load((LETTER_DIR / "manifest.yaml").read_text(encoding="utf-8"))
    return LetterManifest.model_validate(data)


def french_date(day: date) -> str:
    first = "1er" if day.day == 1 else str(day.day)
    return f"{first} {_MONTHS[day.month - 1]} {day.year}"


# French typography: a figure never ends a line apart from its unit.
_UNIT_SPACE = re.compile(r"(?<=\d) (?=%|€|k€)")


def paragraphs(text: str) -> list[str]:
    """A slot's text as paragraphs, split on blank lines."""
    return [
        _UNIT_SPACE.sub("\u00a0", " ".join(block.split()))
        for block in text.split("\n\n")
        if block.strip()
    ]


def render_letter(
    texts: dict[str, str],
    identity: Identity,
    *,
    offer_title: str,
    recipient: str,
    day: date,
    letter_dir: Path = LETTER_DIR,
) -> RenderedLetter:
    manifest = load_letter_manifest()
    environment = Environment(
        loader=FileSystemLoader(letter_dir), undefined=StrictUndefined, autoescape=True
    )
    html = environment.get_template("template.html").render(
        lang=manifest.langs[0],
        title=f"Lettre — {identity.name}" if identity.name else "Lettre de motivation",
        identity=identity,
        date=f"Le {french_date(day)}",
        recipient=recipient,
        offer_title=offer_title,
        slots={spec.name: paragraphs(texts.get(spec.name, "")) for spec in manifest.slots},
    )
    css = (letter_dir / "style.css").read_text(encoding="utf-8")
    pdf, pages = render_pdf(html, css, letter_dir)
    return RenderedLetter(pdf=pdf, pages=pages)

"""Post-render check: the PDF's own text must carry every selected item, in order."""

import io
import re
from typing import Literal, NamedTuple

from pypdf import PdfReader

from jobingo.domain.cv_selection import CvSelection
from jobingo.render.cv import SECTION_LABELS

_WHITESPACE_RE = re.compile(r"\s+")


class PdfProblem(NamedTuple):
    kind: Literal["section_missing", "item_missing", "item_out_of_sequence"]
    subject: str  # a section's label or an item's id


def extract_pdf_text(pdf: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def compact(text: str) -> str:
    """The text with every space removed. The renderer may break a line after a slash
    (`Java/Spring/` then `Jakarta`), which the extracted text reads back as
    `Java/Spring/ Jakarta`; comparing without spaces is immune to where a line broke,
    and still checks the characters and their order."""
    return _WHITESPACE_RE.sub("", text)


def verify_cv_pdf(pdf: bytes, selection: CvSelection) -> list[PdfProblem]:
    """What is wrong with the rendered PDF. An empty list means it faithfully carries the
    selection.

    A side panel that runs past its page is cut, with no extra page to count, so this is
    the only way to learn about it. Over one page, the panel's text is expected out of
    sequence: it stays on page 1, between the main column's pages.
    """
    problems: list[PdfProblem] = []
    text = compact(extract_pdf_text(pdf))

    expected_sections = [
        (SECTION_LABELS["experiences"], bool(selection.experiences)),
        (SECTION_LABELS["projets"], bool(selection.projets)),
        (SECTION_LABELS["formation"], bool(selection.formation)),
        (SECTION_LABELS["competences"], bool(selection.competences)),
        (SECTION_LABELS["loisirs"], selection.options.loisirs and bool(selection.loisirs)),
    ]
    for label, expected in expected_sections:
        if expected and compact(label) not in text:
            problems.append(PdfProblem("section_missing", label))

    cursor = 0
    for item in selection.kept_items():
        needle = compact(item.text)
        position = text.find(needle, cursor)
        if position != -1:
            cursor = position + len(needle)
        elif needle in text:
            problems.append(PdfProblem("item_out_of_sequence", item.id))
        else:
            problems.append(PdfProblem("item_missing", item.id))
    return problems

"""Gaps the model leaves for the user to fill, and their detection.

When a reply needs a fact the model was not given (the user's availabilities,
a date, a salary expectation), it must not invent it. From prompt v4 on it
writes one fixed marker instead, `[À COMPLÉTER : <libellé>]`, with a label from
`PLACEHOLDER_LABELS`, so the gap is visible and the code can find it exactly.

Detection does not trust the model to follow that format: anything that reads
as a placeholder (text in square or curly brackets, `XX`, `___`, `???`, the
`[CANDIDAT]` redaction marker) is found too. Nothing with a placeholder in it may
leave the machine: a message cannot be queued for sending until every marker is
replaced.
"""

import re
from dataclasses import dataclass

from jobingo.domain.text import fold

PLACEHOLDER_PREFIX = "À COMPLÉTER"

# The labels the model may use, most frequent first. `précision` is the
# catch-all, so the format never has to change for a gap the list misses.
# `draft_reply.v4.system.md` lists them verbatim (`test_prompts.py` checks it).
PLACEHOLDER_LABELS: tuple[str, ...] = (
    "disponibilités",
    "date",
    "heure",
    "lieu",
    "interlocuteur",
    "prétentions salariales",
    "date de prise de poste",
    "précision",
)

_FOLDED_LABELS = {fold(label): label for label in PLACEHOLDER_LABELS}

# The canonical marker, accents and case aside: « [à completer : date] » counts.
_CANONICAL_RE = re.compile(r"\[\s*a\s+completer\s*:\s*([^\[\]\n]{1,60}?)\s*\]", re.IGNORECASE)
# Anything else that reads as a gap. Square brackets need a letter inside and
# must not open a Markdown link (`[texte](url)`); angle brackets are left alone
# (an e-mail address is written `<a@b.fr>`).
_OTHER_RES = (
    re.compile(r"\[[^\[\]\n]*[^\W\d_][^\[\]\n]*\](?!\()"),
    re.compile(r"\{\{?[^{}\n]{1,60}\}?\}"),
    re.compile(r"(?<!\w)X{2,}(?:[/.\-]X{2,})*(?!\w)"),
    re.compile(r"_{3,}"),
    re.compile(r"\?{3,}"),
)


def format_placeholder(label: str) -> str:
    return f"[{PLACEHOLDER_PREFIX} : {label}]"


@dataclass(frozen=True)
class Placeholder:
    text: str  # as written in the draft
    label: str | None = None  # the vocabulary label when the marker is canonical

    @property
    def canonical(self) -> bool:
        return self.label is not None


def find_placeholders(text: str) -> list[Placeholder]:
    """Every gap left in `text`, in order and without repeats."""
    found: dict[int, Placeholder] = {}
    folded = fold(text)  # same length as `text` for Latin text: offsets stay valid
    same_length = len(folded) == len(text)
    covered: list[tuple[int, int]] = []
    if same_length:
        for match in _CANONICAL_RE.finditer(folded):
            label = _FOLDED_LABELS.get(fold(match.group(1)).strip())
            found[match.start()] = Placeholder(text[match.start() : match.end()], label)
            covered.append(match.span())
    for pattern in _OTHER_RES:
        for match in pattern.finditer(text):
            if any(start <= match.start() < end for start, end in covered):
                continue
            found.setdefault(match.start(), Placeholder(match.group(0)))
            covered.append(match.span())
    unique: dict[str, Placeholder] = {}
    for _start, placeholder in sorted(found.items()):
        unique.setdefault(placeholder.text, placeholder)
    return list(unique.values())


def placeholders_message(placeholders: list[Placeholder]) -> str:
    """The sentence the screens show and the refusal carries."""
    listed = ", ".join(f"« {p.text} »" for p in placeholders)
    return f"à compléter avant l'envoi : {listed}"

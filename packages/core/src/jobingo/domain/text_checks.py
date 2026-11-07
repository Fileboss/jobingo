"""Deterministic checks on text the model wrote.

A rewrite may not introduce a number absent from its source. A proper noun absent from
the source is only flagged for the user to check, never refused: capitalisation cannot
tell a name from an acronym such as "POC".
"""

import re

from jobingo.domain.text import fold

# A digit run, optionally decimal, optionally a percentage. Spaces between digits go
# first, so the French "40 000" and "40000" are the same token.
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?%?")
_DIGIT_SPACE_RE = re.compile(r"(?<=\d)[\s  ](?=\d)")
_PERCENT_SPACE_RE = re.compile(r"[\s  ]+%")
_CAPITALIZED_RE = re.compile(r"[A-ZÀ-ÖØ-Þ][\wÀ-ɏ'’-]*")
_WORD_RE = re.compile(r"[\wÀ-ɏ'’-]+")


def numbers_in(text: str) -> list[str]:
    canonical = _PERCENT_SPACE_RE.sub("%", _DIGIT_SPACE_RE.sub("", text))
    return [match.replace(",", ".") for match in _NUMBER_RE.findall(canonical)]


def _opens_sentence(text: str, index: int) -> bool:
    before = text[:index].rstrip()
    return not before or before[-1] in ".!?:;•-–—\n"


def proper_nouns_in(text: str) -> list[str]:
    """Capitalised words that do not open a sentence. Biased towards flagging: a false
    positive only costs the user a glance."""
    return [
        match.group(0)
        for match in _CAPITALIZED_RE.finditer(text)
        if not _opens_sentence(text, match.start())
    ]


def unsourced_proper_nouns(text: str, source: str) -> list[str]:
    """The proper nouns of `text` that `source` never mentions, in order, once each."""
    known = {fold(word) for word in _WORD_RE.findall(source)}
    unsourced: list[str] = []
    for noun in proper_nouns_in(text):
        if fold(noun) not in known and noun not in unsourced:
            unsourced.append(noun)
    return unsourced


def count_words(text: str) -> int:
    return len(_WORD_RE.findall(text))

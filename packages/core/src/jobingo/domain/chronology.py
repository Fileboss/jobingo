"""Reverse-chronological order for experiences and education.

The model picks these sections, it does not order them: the code sorts by the dates
written in each title, most recent first, as a CV is read.
"""

import re
from collections.abc import Callable

from jobingo.domain.text import fold

_MONTHS = {
    name: number
    for number, names in enumerate(
        [
            ("janvier", "january"),
            ("fevrier", "february"),
            ("mars", "march"),
            ("avril", "april"),
            ("mai", "may"),
            ("juin", "june"),
            ("juillet", "july"),
            ("aout", "august"),
            ("septembre", "september"),
            ("octobre", "october"),
            ("novembre", "november"),
            ("decembre", "december"),
        ],
        start=1,
    )
    for name in names
}
_DATE_RE = re.compile(
    r"(?P<mm>\d{1,2})/(?P<mmy>\d{4})"
    r"|(?P<month>[a-z]+)\s+(?P<my>\d{4})"
    r"|(?P<year>\b(?:19|20)\d{2}\b)"
)
# Whole words only: otherwise « représentant » or « concurrent » made a past position
# look ongoing.
_NOW_RE = re.compile(
    r"\b(?:aujourd'?hui|aujourd|present|en cours|current|currently|now|to date|depuis|since)\b"
)
_ONGOING = (9999, 12)

type Month = tuple[int, int]


def _dates(text: str) -> list[Month]:
    found: list[Month] = []
    for match in _DATE_RE.finditer(text):
        if match["mm"]:
            month = int(match["mm"])
            if 1 <= month <= 12:
                found.append((int(match["mmy"]), month))
        elif match["month"]:
            month = _MONTHS.get(match["month"])
            if month:
                found.append((int(match["my"]), month))
            elif re.fullmatch(r"(19|20)\d{2}", match["my"]):
                found.append((int(match["my"]), 1))
        else:
            found.append((int(match["year"]), 1))
    return found


def chronology_key(text: str) -> tuple[Month, Month] | None:
    """`(end, start)` of the period a title states, None when it states no date."""
    plain = fold(text).replace("’", "'")
    dates = _dates(plain)
    if not dates:
        return None
    start = dates[0]
    end = _ONGOING if _NOW_RE.search(plain) else dates[-1]
    return (max(start, end), start)


def sort_reverse_chronological[T](items: list[T], text_of: Callable[[T], str]) -> list[T]:
    """Most recent first. Undated items go last in their given order; the sort is
    stable, so equal periods keep theirs."""
    keyed = [(chronology_key(text_of(item)), item) for item in items]
    dated = sorted(
        ((key, item) for key, item in keyed if key is not None),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return [item for _, item in dated] + [item for key, item in keyed if key is None]

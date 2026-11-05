"""The CV as the user edits it, and as the application stores it.

The stored Markdown carries a ``<!-- id=… tags=… -->`` comment on every element:
the ids are the key of selection, scoring and the archived documents. Nobody
should have to type them, so the editor shows a *clean view* (`to_clean_view`:
comments gone, tags written ``#python #api`` at the end of the line) and
`normalize_cv` turns what the user typed back into the stored form:

- a line that already has an id keeps it (hand-written ids);
- the others are matched with the previous version, by text first, then by
  similarity, so an edited element keeps its id and a moved one too;
- what is left gets a fresh readable id (``nordlys``, ``nordlys-03``);
- an id that disappeared is *retired* (front matter ``retired:``) and never
  given again.

Pure functions on text: the writing stays in `services.cv_editor`.
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

import yaml

from jobingo.domain.frontmatter import lenient_front_matter, split_front_matter
from jobingo.domain.profile import (
    COMMENT_RE,
    ProfileItem,
    extract_comment,
    parse_comment,
    parse_cv_markdown,
    scan_cv_body,
    split_comment_tags,
)
from jobingo.domain.text import fold

_FRONT_RE = re.compile(r"\A---[ \t]*\n.*?\n---[ \t]*(?:\n|\Z)", re.S)
TRAILING_TAGS_RE = re.compile(r"(?:\s+#[^\W\d_][\w.+-]*)+\s*$")
_SIMILARITY = 0.6
_ID_PREFIX = {"formation": "edu", "skill": "skill", "hobby": "hobby", "resume": "resume"}


@dataclass(eq=False)
class _Entry:
    line: int
    kind: str  # resume | experience | formation | bullet | skill | hobby
    prefix: str
    text: str
    tags: list[str]
    explicit_id: str | None
    keep_raw: bool  # already in stored form: leave the line byte for byte
    parent: "_Entry | None" = None
    id: str = ""


def split_head(text: str) -> tuple[str, str, str]:
    """(text with `\\n` line endings, front matter block, body). A block that is
    not valid front matter is body, so it can never make a CV unsaveable."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    match = _FRONT_RE.match(text)
    if match is None:
        return text, "", text
    try:
        split_front_matter(text)
    except ValueError:
        return text, "", text
    head = match.group(0)
    return text, head, text[len(head) :]


def _front_matter(metadata: dict[str, Any]) -> str:
    if not metadata:
        return ""
    return "---\n" + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True) + "---\n"


def _entry(line: int, kind: str, prefix: str, raw_text: str, parent: "_Entry | None") -> _Entry:
    text, meta = extract_comment(raw_text)
    typed = TRAILING_TAGS_RE.search(text)
    typed_tags: list[str] = []
    if typed:
        typed_tags = [word[1:] for word in typed.group(0).split()]
        text = text[: typed.start()].rstrip()
    tags = split_comment_tags(meta.get("tags"))
    tags += [tag for tag in typed_tags if tag not in tags]
    explicit = meta.get("id")
    return _Entry(
        line=line,
        kind=kind,
        prefix=prefix,
        text=text,
        tags=tags,
        explicit_id=explicit,
        keep_raw=bool(explicit) and not typed_tags,
        parent=parent,
    )


def _scan(lines: list[str]) -> list[_Entry]:
    """The lines that carry an element, as `parse_cv_markdown` reads them."""
    entries: list[_Entry] = []
    by_line: dict[int, _Entry] = {}
    for scanned in scan_cv_body(lines):
        if scanned.role != "item":
            continue
        parent = by_line.get(scanned.parent) if scanned.parent is not None else None
        entry = _entry(scanned.index, scanned.kind, scanned.prefix, scanned.raw, parent)
        entries.append(entry)
        by_line[scanned.index] = entry
    return entries


def _match(entries: list[_Entry], old: list[ProfileItem]) -> None:
    """Give each entry the id of the old element it is: same text, else the most
    similar one (an edit). What is not matched stays without id."""
    free = list(old)
    pending = list(entries)
    for entry in list(pending):
        for item in free:
            if item.text == entry.text:
                entry.id = item.id
                free.remove(item)
                pending.remove(entry)
                break
    scored = sorted(
        (
            (SequenceMatcher(None, fold(e.text), fold(o.text)).ratio(), n, m)
            for n, e in enumerate(pending)
            for m, o in enumerate(free)
        ),
        key=lambda t: -t[0],
    )
    taken_new: set[int] = set()
    taken_old: set[int] = set()
    for ratio, n, m in scored:
        if ratio < _SIMILARITY:
            break
        if n in taken_new or m in taken_old:
            continue
        pending[n].id = free[m].id
        taken_new.add(n)
        taken_old.add(m)


def _slug(text: str) -> str:
    first = re.split(r"\s[—–-]\s|,|\(", text, maxsplit=1)[0]
    slug = re.sub(r"[^a-z0-9]+", "-", fold(first)).strip("-")[:24].strip("-")
    return slug or "exp"


def _fresh(entry: _Entry, used: set[str]) -> str:
    if entry.kind == "experience":
        base = _slug(entry.text)
        candidate, n = base, 2
        while candidate in used:
            candidate = f"{base}-{n}"
            n += 1
        return candidate
    prefix = entry.parent.id if entry.parent else _ID_PREFIX.get(entry.kind, "item")
    n = 1
    while f"{prefix}-{n:02d}" in used:
        n += 1
    return f"{prefix}-{n:02d}"


def _comment(entry: _Entry) -> str:
    tags = f" tags={','.join(entry.tags)}" if entry.tags else ""
    return f"<!-- id={entry.id}{tags} -->"


def _retired_ids(metadata: dict[str, Any]) -> list[str]:
    retired = metadata.get("retired")
    return [str(x) for x in retired] if isinstance(retired, list) else []  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]


def normalize_cv(typed: str, previous: str = "") -> str:
    """The stored Markdown for what the user typed in the editor, ids attached.
    `previous` is the CV as stored before this edit ("" for a first save)."""
    text, head, body = split_head(typed)
    metadata = split_front_matter(text)[0] if head else {}
    previous = previous.replace("\r\n", "\n")
    old_items = parse_cv_markdown(previous).items if previous.strip() else []
    retired = _retired_ids(lenient_front_matter(previous)[0]) if previous.strip() else []

    lines = body.split("\n")
    entries = _scan(lines)
    for entry in entries:
        if entry.explicit_id in retired:
            # Pasted from an old copy: a retired id never comes back.
            entry.explicit_id, entry.keep_raw = None, False
    explicit = {e.explicit_id for e in entries if e.explicit_id}
    for entry in entries:
        if entry.explicit_id:
            entry.id = entry.explicit_id

    pool = [o for o in old_items if o.id not in explicit]
    todo = [e for e in entries if not e.id]
    top = [e for e in todo if e.kind != "bullet"]
    for kind in {e.kind for e in top}:
        _match([e for e in top if e.kind == kind], [o for o in pool if o.kind == kind])

    used = {o.id for o in old_items} | set(retired) | explicit | {e.id for e in entries if e.id}
    for entry in top:
        if not entry.id:
            entry.id = _fresh(entry, used)
            used.add(entry.id)

    parents = {id(e.parent): e.parent for e in todo if e.kind == "bullet"}
    for key, parent in parents.items():
        group = [e for e in todo if e.kind == "bullet" and id(e.parent) == key]
        parent_id = parent.id if parent else None
        _match(group, [o for o in pool if o.kind == "bullet" and o.parent_id == parent_id])
    # A bullet moved under another experience keeps its id too.
    taken = {e.id for e in entries if e.id}
    _match(
        [e for e in todo if e.kind == "bullet" and not e.id],
        [o for o in pool if o.kind == "bullet" and o.id not in taken],
    )
    used |= {e.id for e in entries if e.id}
    for entry in todo:
        if not entry.id:
            entry.id = _fresh(entry, used)
            used.add(entry.id)

    for entry in entries:
        if not entry.keep_raw:
            lines[entry.line] = f"{entry.prefix}{entry.text} {_comment(entry)}"

    kept = {e.id for e in entries}
    for item in old_items:
        if item.id not in kept and item.id not in retired:
            retired.append(item.id)
    if retired:
        head = _front_matter({**metadata, "retired": retired}) + ("\n" if not head else "")
    return head + "\n".join(lines)


def to_clean_view(stored: str) -> str:
    """The stored Markdown without the id comments (tags become ``#tag``) and
    without the retired-ids list."""
    text, head, body = split_head(stored)
    if head:
        metadata = split_front_matter(text)[0]
        if "retired" in metadata:
            metadata = {k: v for k, v in metadata.items() if k != "retired"}
            head = _front_matter(metadata)
            if not head:
                # The blank line `normalize_cv` added after a block it created.
                body = body.removeprefix("\n")
    lines: list[str] = []
    for line in body.split("\n"):
        match = COMMENT_RE.search(line)
        meta = parse_comment(match.group(1)) if match else {}
        if match and "id" in meta:
            line = line[: match.start()].rstrip()
            line += "".join(f" #{tag}" for tag in split_comment_tags(meta.get("tags")))
        lines.append(line)
    return head + "\n".join(lines)

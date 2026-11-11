"""The CV as a form: the same document, seen field by field.

The form reads the *clean view* of the stored CV (`cv_markdown.to_clean_view`)
and writes a clean view back, which `canonical_stored` turns into the stored
form. So the form adds no way of writing the CV.

**Invariant: the form and the Markdown are the same thing.** Every save, from
either view, stores `canonical_stored(...)`, a fixed point of the round trip:
for a stored CV ``S``, ``fields_to_markdown(parse_fields(to_clean_view(S)))
== to_clean_view(S)``. So opening the form and saving it without a change
rewrites nothing, and the text view shows exactly what the form holds:

- a section the form can show field by field (only the lines it understands) is
  shown as fields; any other content (an unknown section, a section with a line
  the form cannot represent, a section written twice) is one block of
  ``others``, written back as it was, at its place;
- the sections keep the order of the document (``order``); a section filled in
  the form that the document did not have goes at its usual place among the others;
- an experience title ``Entreprise — Poste — début – fin`` is split into fields
  only when joining them again gives the very same text, otherwise the title is
  one free field;
- the front matter is kept as it is.

A new field must round-trip through `parse_fields`/`fields_to_markdown` or the
invariant breaks. Pure functions on text.
"""

import re

from pydantic import BaseModel, ConfigDict

from jobingo.domain.cv_markdown import (
    TRAILING_TAGS_RE,
    normalize_cv,
    split_head,
    to_clean_view,
)
from jobingo.domain.profile import (
    BULLET_RE,
    COMPETENCES_SECTION,
    EXPERIENCES_SECTION,
    FORMATION_SECTION,
    HEADING_RE,
    KNOWN_SECTIONS,
    LOISIRS_SECTION,
    PROJETS_SECTION,
    RESUME_SECTION,
    canonical_section,
    extract_comment,
)

_TAG_WORD_RE = re.compile(r"[^\W\d_][\w.+-]*")
_TITLE_SEP_RE = re.compile(r"\s+—\s+")
_DATES_SEP_RE = re.compile(r"\s+–\s+")
_MARKER_RE = re.compile(r"^(?:[-*+]|\d+[.)])\s+")

# Written for an experience that has achievements and no title: without a title line
# they would belong to the experience above. Diagnostics point at it (`missing_title`).
UNTITLED_EXPERIENCE = "Expérience sans intitulé"


class _Fields(BaseModel):
    # The defaults are for building a value in code. The client always receives every
    # field and sends them all back, so the contract has one schema, all fields required.
    model_config = ConfigDict(
        json_schema_mode_override="serialization",
        json_schema_serialization_defaults_required=True,
    )


class ExperienceFields(_Fields):
    company: str = ""
    role: str = ""
    start: str = ""
    end: str = ""
    title: str = ""  # the free title, used when `structured` is False
    structured: bool = True
    tags: list[str] = []
    bullets: list[str] = []  # keywords written ``#tag`` at the end of the text

    def full_title(self) -> str:
        if not self.structured:
            return _one_line(self.title)
        dates = " – ".join(part for part in (_one_line(self.start), _one_line(self.end)) if part)
        parts = (_one_line(self.company), _one_line(self.role), dates)
        return " — ".join(part for part in parts if part)

    def is_empty(self) -> bool:
        return not self.full_title() and not _lines(self.bullets) and not self.tags


class FormationEntry(_Fields):
    text: str = ""
    heading: bool = False  # a ``###`` line rather than a ``-`` line


class CvFields(_Fields):
    front: str = ""
    resume: str = ""
    experiences: list[ExperienceFields] = []
    formation: list[FormationEntry] = []
    skills: list[str] = []
    hobbies: list[str] = []
    projects: list[str] = []
    before: str = ""  # text before the first section
    others: list[str] = []  # blocks the form cannot show, in Markdown
    # The sections in document order: keys of `SECTION_KEYS`, and OTHER for the next
    # block of `others`.
    order: list[str] = []


OTHER = "other"
SECTION_KEYS = ("resume", "experiences", "projects", "formation", "skills", "hobbies")
_KEY_OF_SECTION = {
    RESUME_SECTION: "resume",
    EXPERIENCES_SECTION: "experiences",
    FORMATION_SECTION: "formation",
    COMPETENCES_SECTION: "skills",
    LOISIRS_SECTION: "hobbies",
    PROJETS_SECTION: "projects",
}


def _one_line(value: str) -> str:
    return " ".join(value.split())


def split_tags(words: list[str]) -> tuple[list[str], list[str]]:
    """(keywords, rejected words) of keywords typed with or without ``#``."""
    good: list[str] = []
    bad: list[str] = []
    for value in words:
        for word in re.split(r"[\s,]+", value.strip()):
            word = word.lstrip("#")
            if not word:
                continue
            if _TAG_WORD_RE.fullmatch(word):
                if word not in good:
                    good.append(word)
            else:
                bad.append(word)
    return good, bad


def _decompose(title: str) -> ExperienceFields:
    parts = _TITLE_SEP_RE.split(title)
    candidate = ExperienceFields(title=title, structured=False)
    if len(parts) == 3 and all(parts):
        dates = _DATES_SEP_RE.split(parts[2])
        start, end = (dates[0], dates[1]) if len(dates) == 2 else (parts[2], "")
        candidate = ExperienceFields(company=parts[0], role=parts[1], start=start, end=end)
    elif len(parts) == 2 and all(parts):
        # Not everybody fills every field: keep what was typed in the same fields.
        if parts[1][0].isdigit():
            dates = _DATES_SEP_RE.split(parts[1])
            start, end = (dates[0], dates[1]) if len(dates) == 2 else (parts[1], "")
            candidate = ExperienceFields(company=parts[0], start=start, end=end)
        else:
            candidate = ExperienceFields(company=parts[0], role=parts[1])
    if candidate.full_title() == title:
        return candidate
    return ExperienceFields(title=title, structured=False)


def split_title(title: str) -> tuple[str, str]:
    """(the title without its dates, the dates), the dates being what the form's own
    fields would hold. A title the form keeps as one free field has none."""
    fields = _decompose(title)
    if not fields.structured:
        return title, ""
    dates = " – ".join(part for part in (fields.start, fields.end) if part)
    return " — ".join(part for part in (fields.company, fields.role) if part), dates


def _bullets(lines: list[str]) -> list[str] | None:
    """The text of each bullet, None if a line is not a plain top-level bullet."""
    texts: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        match = BULLET_RE.match(line.rstrip())
        if not match:
            return None
        texts.append(match.group(1).strip())
    return texts


def _fill_experiences(lines: list[str]) -> list[ExperienceFields] | None:
    result: list[ExperienceFields] = []
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue
        heading = HEADING_RE.match(line)
        if heading:
            if heading.group(1) != "###":
                return None
            title = extract_comment(heading.group(2))[0]
            tags = TRAILING_TAGS_RE.search(title)
            tag_words: list[str] = []
            if tags:
                tag_words = [word[1:] for word in tags.group(0).split()]
                title = title[: tags.start()].rstrip()
            experience = _decompose(title)
            experience.tags = tag_words
            result.append(experience)
            continue
        bullet = BULLET_RE.match(line)
        if not bullet or not result:
            return None
        result[-1].bullets.append(bullet.group(1).strip())
    return result


def _fill_formation(lines: list[str]) -> list[FormationEntry] | None:
    out: list[FormationEntry] = []
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue
        heading = HEADING_RE.match(line)
        if heading and heading.group(1) == "###":
            out.append(FormationEntry(text=heading.group(2).strip(), heading=True))
            continue
        bullet = BULLET_RE.match(line)
        if not bullet:
            return None
        out.append(FormationEntry(text=bullet.group(1).strip()))
    return out


def _paragraphs(value: str) -> str:
    """Lines stripped, runs of blank lines down to one, none at either end."""
    out: list[str] = []
    for line in value.splitlines():
        line = line.strip()
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip("\n")


def _fill_resume(lines: list[str]) -> str | None:
    if any(HEADING_RE.match(line.strip()) for line in lines if line.strip()):
        return None
    return _paragraphs("\n".join(lines))


def parse_fields(clean: str) -> CvFields:
    """The fields of a CV in clean view (see the module docstring)."""
    text, front, body = split_head(clean)
    chunks: list[tuple[str, list[str]]] = [("", [])]  # (``## `` heading line, body lines)
    for line in text[len(front) :].split("\n") if front else body.split("\n"):
        heading = HEADING_RE.match(line.rstrip())
        if heading and heading.group(1) == "##":
            chunks.append((line.rstrip(), []))
        else:
            chunks[-1][1].append(line)

    fields = CvFields(front=front)
    taken: set[str] = set()

    def keep(heading: str, lines: list[str]) -> None:
        block = "\n".join([heading, *lines] if heading else lines).strip("\n")
        if block.strip():
            fields.others.append(block)
            fields.order.append(OTHER)

    fields.before = "\n".join(chunks[0][1]).strip("\n")
    for heading, lines in chunks[1:]:
        section = canonical_section(extract_comment(heading[3:])[0]) if heading else ""
        if section not in KNOWN_SECTIONS or section in taken:
            keep(heading, lines)
            continue
        if section == RESUME_SECTION:
            resume = _fill_resume(lines)
            if resume is None:
                keep(heading, lines)
                continue
            fields.resume = resume
        elif section == EXPERIENCES_SECTION:
            experiences = _fill_experiences(lines)
            if experiences is None:
                keep(heading, lines)
                continue
            fields.experiences = experiences
        elif section == FORMATION_SECTION:
            formation = _fill_formation(lines)
            if formation is None:
                keep(heading, lines)
                continue
            fields.formation = formation
        else:
            texts = _bullets(lines)
            if texts is None:
                keep(heading, lines)
                continue
            if section == COMPETENCES_SECTION:
                fields.skills = texts
            elif section == PROJETS_SECTION:
                fields.projects = texts
            else:
                fields.hobbies = texts
        taken.add(section)
        fields.order.append(_KEY_OF_SECTION[section])
    return fields


def _lines(values: list[str]) -> list[str]:
    """The non-blank lines of a list of inputs, a bullet marker typed by habit removed."""
    return [
        _MARKER_RE.sub("", line.strip())
        for value in values
        for line in value.splitlines()
        if line.strip()
    ]


def _bullet_block(values: list[str]) -> str:
    return "\n".join(f"- {line}" for line in _lines(values))


def _formation_block(entries: list[FormationEntry]) -> str:
    return "\n".join(
        f"{'### ' if entry.heading else '- '}{line}"
        for entry in entries
        for line in _lines([entry.text])
    )


def _section_blocks(fields: CvFields) -> dict[str, str]:
    """The Markdown of each known section the fields fill."""
    blocks: dict[str, str] = {}
    if fields.resume.strip():
        blocks["resume"] = f"## {RESUME_SECTION}\n\n{_paragraphs(fields.resume)}"
    experiences: list[str] = []
    for experience in fields.experiences:
        if experience.is_empty():
            continue
        words = split_tags(experience.tags)[0]
        title = experience.full_title() or UNTITLED_EXPERIENCE
        block = "### " + title + "".join(f" #{word}" for word in words)
        bullets = _bullet_block(experience.bullets)
        if bullets:
            block += "\n\n" + bullets
        experiences.append(block)
    if experiences:
        blocks["experiences"] = f"## {EXPERIENCES_SECTION}\n\n" + "\n\n".join(experiences)
    formation = _formation_block(fields.formation)
    if formation:
        blocks["formation"] = f"## {FORMATION_SECTION}\n\n{formation}"
    skills = _bullet_block(fields.skills)
    if skills:
        blocks["skills"] = f"## {COMPETENCES_SECTION}\n\n{skills}"
    hobbies = _bullet_block(fields.hobbies)
    if hobbies:
        blocks["hobbies"] = f"## {LOISIRS_SECTION}\n\n{hobbies}"
    projects = _bullet_block(fields.projects)
    if projects:
        blocks["projects"] = f"## {PROJETS_SECTION}\n\n{projects}"
    return blocks


def _ordered_keys(fields: CvFields, present: set[str]) -> list[str]:
    """`fields.order`, cleaned (unknown keys, repeats and extra OTHER dropped,
    missing OTHER added at the end), with each filled section the document did
    not have inserted after the last section that usually comes before it."""
    keys: list[str] = []
    others = 0
    for key in fields.order:
        if key == OTHER:
            if others < len(fields.others):
                keys.append(key)
                others += 1
        elif key in SECTION_KEYS and key not in keys:
            keys.append(key)
    keys += [OTHER] * (len(fields.others) - others)
    for rank, key in enumerate(SECTION_KEYS):
        if key not in present or key in keys:
            continue
        before = [i for i, k in enumerate(keys) if k in SECTION_KEYS[:rank]]
        after = [i for i, k in enumerate(keys) if k in SECTION_KEYS[rank + 1 :]]
        position = before[-1] + 1 if before else (after[0] if after else len(keys))
        keys.insert(position, key)
    return keys


def fields_to_markdown(fields: CvFields, lang: str = "fr") -> str:
    """The clean-view Markdown of the fields."""
    sections = _section_blocks(fields)
    others = iter(fields.others)
    blocks: list[str] = []
    before = fields.before.replace("\r\n", "\n").strip("\n")
    if before.strip():
        blocks.append(before)
    for key in _ordered_keys(fields, set(sections)):
        if key == OTHER:
            block = next(others).replace("\r\n", "\n").strip("\n")
        else:
            block = sections.get(key, "")
        if block.strip():
            blocks.append(block)

    front = fields.front
    if not front and lang != "fr" and blocks:
        front = f"---\nlang: {lang}\n---\n"
    head = front + "\n" if front else ""
    return head + "\n\n".join(blocks) + ("\n" if blocks else "")


def canonical_stored(content: str, previous: str, lang: str = "fr") -> str:
    """What a save stores for `content` (either view's text): ids attached against
    `previous` (`normalize_cv`), then put in the form's layout, so the stored CV
    is a fixed point of form → text → form."""
    stored = normalize_cv(content, previous)
    canonical = fields_to_markdown(parse_fields(to_clean_view(stored)), lang)
    return normalize_cv(canonical, stored)

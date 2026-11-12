import re
from dataclasses import dataclass

from pydantic import BaseModel

from jobingo.domain.frontmatter import lenient_front_matter
from jobingo.domain.text import fold

HEADING_RE = re.compile(r"^(#{2,3})\s+(.*)$")
# A top-level bullet: `-`, `*`, `+` or a numbered item (`1.`, `2)`).
BULLET_RE = re.compile(r"^(?:[-*+]|\d+[.)])\s+(.*)$")
_NESTED_BULLET_RE = re.compile(r"^[ \t]+(?:[-*+]|\d+[.)])\s+(.*)$")
# An experience written as a line in bold: `**Entreprise — Poste — dates**`.
_BOLD_RE = re.compile(r"^\*\*(.+?)\*\*[ \t]*(<!--.*?-->)?[ \t]*$")
COMMENT_RE = re.compile(r"<!--\s*(.*?)\s*-->\s*$")
_KV_RE = re.compile(r"(\w+)=(\S+)")

RESUME_SECTION = "Résumé"
EXPERIENCES_SECTION = "Expériences"
FORMATION_SECTION = "Formation"
COMPETENCES_SECTION = "Compétences"
LANGUES_SECTION = "Langues"
LOISIRS_SECTION = "Loisirs"
PROJETS_SECTION = "Projets personnels"

KNOWN_SECTIONS = (
    RESUME_SECTION,
    EXPERIENCES_SECTION,
    PROJETS_SECTION,
    FORMATION_SECTION,
    COMPETENCES_SECTION,
    LANGUES_SECTION,
    LOISIRS_SECTION,
)


# Section titles are recognised without case or accents, with a few synonyms; an
# unknown title is kept as written and its content is ignored by the flows.
_SECTION_SYNONYMS = {
    RESUME_SECTION: ("resume", "profil", "summary"),
    EXPERIENCES_SECTION: (
        "experiences",
        "experience",
        "experience professionnelle",
        "experiences professionnelles",
        "parcours professionnel",
        "work experience",
    ),
    FORMATION_SECTION: ("formation", "formations", "education"),
    COMPETENCES_SECTION: ("competences", "competence", "skills"),
    LANGUES_SECTION: ("langues", "langue", "langues etrangeres", "languages"),
    LOISIRS_SECTION: ("loisirs", "centres d'interet", "interests", "hobbies"),
    PROJETS_SECTION: (
        "projets personnels",
        "projet personnel",
        "projets",
        "side projects",
        "personal projects",
        "projects",
    ),
}


def canonical_section(title: str) -> str:
    folded = " ".join(fold(title).split())
    for canonical, names in _SECTION_SYNONYMS.items():
        if folded in names:
            return canonical
    return title


class ProfileItem(BaseModel):
    id: str
    kind: str  # resume | experience | formation | bullet | skill | language | hobby | project
    text: str
    section: str
    tags: list[str] = []
    line_no: int
    parent_id: str | None = None
    heading: bool = False  # written as a `###` line


class ProfileError(BaseModel):
    line_no: int
    kind: str  # duplicate_id | missing_id
    section: str
    message: str


class Profile(BaseModel):
    lang: str
    items: list[ProfileItem] = []
    errors: list[ProfileError] = []

    @property
    def is_valid(self) -> bool:
        return not any(error.kind == "duplicate_id" for error in self.errors)

    def ids(self) -> set[str]:
        return {item.id for item in self.items}


def parse_comment(comment: str) -> dict[str, str]:
    return dict(_KV_RE.findall(comment))


def split_comment_tags(value: str | None) -> list[str]:
    if not value:
        return []
    return [tag for tag in value.split(",") if tag]


def extract_comment(text: str) -> tuple[str, dict[str, str]]:
    """Split trailing ``<!-- id=... -->`` comment from a heading/bullet line."""
    match = COMMENT_RE.search(text)
    if not match:
        return text.strip(), {}
    return COMMENT_RE.sub("", text).strip(), parse_comment(match.group(1))


@dataclass(frozen=True)
class ScannedLine:
    """One line of a CV body that means something to the parser.

    `role` is ``section`` (a ``##`` title), ``item`` (an element that gets an
    id) or ``ignored`` (a line no flow reads). `prefix` is the marker the
    canonical form writes (``### `` for an experience however it was typed).
    `problem` is a code `cv_diagnostics.diagnose_cv` turns into a message.
    """

    index: int
    role: str
    section: str
    kind: str = ""
    raw: str = ""
    prefix: str = ""
    parent: int | None = None
    problem: str = ""


def _next_line(lines: list[str], index: int) -> str:
    for line in lines[index + 1 :]:
        if line.strip():
            return line.rstrip()
    return ""


def scan_cv_body(lines: list[str]) -> list[ScannedLine]:
    """The single reading of a CV body, shared by `parse_cv_markdown` (items and
    ids), `cv_markdown.normalize_cv` (attaching ids) and `diagnose_cv`: the CV
    syntax changes here only."""
    scanned: list[ScannedLine] = []
    section = ""
    current: int | None = None
    h3_seen = False

    def ignored(index: int, problem: str = "") -> None:
        scanned.append(ScannedLine(index, "ignored", section, problem=problem))

    for index, raw_line in enumerate(lines):
        line = raw_line.rstrip()
        if not line.strip():
            continue

        heading = HEADING_RE.match(line)
        if heading:
            level, title = heading.groups()
            if level == "##":
                section = canonical_section(extract_comment(title)[0])
                current = None
                h3_seen = False
                problem = "" if section in KNOWN_SECTIONS else "unknown_section"
                scanned.append(ScannedLine(index, "section", section, problem=problem))
            elif section in (EXPERIENCES_SECTION, FORMATION_SECTION):
                kind = "experience" if section == EXPERIENCES_SECTION else "formation"
                scanned.append(ScannedLine(index, "item", section, kind, title, "### "))
                current = index
                h3_seen = True
            else:
                ignored(index, "heading_outside")
            continue

        bold = _BOLD_RE.match(line)
        if bold and section in (EXPERIENCES_SECTION, FORMATION_SECTION):
            kind = "experience" if section == EXPERIENCES_SECTION else "formation"
            raw = bold.group(1) + (f" {bold.group(2)}" if bold.group(2) else "")
            scanned.append(ScannedLine(index, "item", section, kind, raw, "### "))
            current = index
            h3_seen = True
            continue

        top = BULLET_RE.match(line)
        nested = _NESTED_BULLET_RE.match(line)
        bullet = top or nested
        if bullet and section in (
            EXPERIENCES_SECTION,
            FORMATION_SECTION,
            COMPETENCES_SECTION,
            LANGUES_SECTION,
            LOISIRS_SECTION,
            PROJETS_SECTION,
        ):
            text = bullet.group(1)
            if section == COMPETENCES_SECTION:
                scanned.append(ScannedLine(index, "item", section, "skill", text, "- "))
            elif section == LANGUES_SECTION:
                scanned.append(ScannedLine(index, "item", section, "language", text, "- "))
            elif section == LOISIRS_SECTION:
                scanned.append(ScannedLine(index, "item", section, "hobby", text, "- "))
            elif section == PROJETS_SECTION:
                scanned.append(ScannedLine(index, "item", section, "project", text, "- "))
            elif section == FORMATION_SECTION:
                scanned.append(ScannedLine(index, "item", section, "formation", text, "- "))
            elif top and not h3_seen and _NESTED_BULLET_RE.match(_next_line(lines, index)):
                # `- Entreprise — Poste` followed by indented bullets: an experience.
                scanned.append(ScannedLine(index, "item", section, "experience", text, "### "))
                current = index
            else:
                problem = "" if current is not None else "orphan_bullet"
                scanned.append(
                    ScannedLine(index, "item", section, "bullet", text, "- ", current, problem)
                )
            continue

        if section == RESUME_SECTION:
            scanned.append(ScannedLine(index, "item", section, "resume", line.strip()))
        elif section == "":
            ignored(index, "title_line" if line.startswith("# ") else "outside_section")
        elif section in KNOWN_SECTIONS:
            ignored(index, "unrecognized_line")
        else:
            ignored(index)
    return scanned


def parse_cv_markdown(text: str) -> Profile:
    metadata, body, body_start_line = lenient_front_matter(text)
    lang = str(metadata.get("lang", "fr"))

    errors: list[ProfileError] = []
    items: list[ProfileItem] = []
    seen_ids: dict[str, int] = {}
    ids_by_index: dict[int, str | None] = {}

    def register(item: ProfileItem) -> None:
        if item.id in seen_ids:
            errors.append(
                ProfileError(
                    line_no=item.line_no,
                    kind="duplicate_id",
                    section=item.section,
                    message=(
                        f"identifiant en double : '{item.id}' "
                        f"(déjà défini ligne {seen_ids[item.id]})"
                    ),
                )
            )
        else:
            seen_ids[item.id] = item.line_no
        items.append(item)

    for line in scan_cv_body(body.splitlines()):
        if line.role != "item":
            continue
        offset = line.index + body_start_line
        clean_text, meta = extract_comment(line.raw)
        item_id = meta.get("id")
        ids_by_index[line.index] = item_id
        if not item_id:
            what = "texte du résumé" if line.kind == "resume" else f"'{clean_text}'"
            errors.append(
                ProfileError(
                    line_no=offset,
                    kind="missing_id",
                    section=line.section,
                    message=f"élément sans identifiant : {what}",
                )
            )
            continue

        # `kind` names the CV element, not the Markdown syntax: a degree listed
        # as a bullet under Formation is a formation item, exactly like one
        # written as an H3.
        register(
            ProfileItem(
                id=item_id,
                kind=line.kind,
                text=clean_text,
                section=line.section,
                tags=[] if line.kind == "resume" else split_comment_tags(meta.get("tags")),
                line_no=offset,
                parent_id=ids_by_index.get(line.parent) if line.parent is not None else None,
                heading=line.prefix == "### ",
            )
        )

    return Profile(lang=lang, items=items, errors=errors)

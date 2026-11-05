"""What the user should know about a CV draft, line by line, with a way out.

Nothing here blocks a save, except a duplicate id (`Profile.is_valid`). The
messages are the user's, in French.
"""

from typing import Literal

from pydantic import BaseModel, Field

from jobingo.domain.cv_fields import UNTITLED_EXPERIENCE, CvFields, split_tags
from jobingo.domain.cv_markdown import split_head
from jobingo.domain.frontmatter import split_front_matter
from jobingo.domain.personal_data import find_personal_data
from jobingo.domain.profile import (
    COMPETENCES_SECTION,
    EXPERIENCES_SECTION,
    FORMATION_SECTION,
    LOISIRS_SECTION,
    ScannedLine,
    extract_comment,
    parse_cv_markdown,
    scan_cv_body,
)

type DiagnosticCode = Literal[
    "duplicate_id",
    "invalid_front_matter",
    "unknown_section",
    "unrecognized_line",
    "heading_outside",
    "orphan_bullet",
    "title_line",
    "outside_section",
    "missing_title",
    "invalid_tag",
    "personal_email",
    "personal_phone",
    "personal_url",
]


class CvDiagnostic(BaseModel):
    code: DiagnosticCode
    level: Literal["error", "warning", "info"]
    line_no: int = Field(
        description=(
            "1-based line of the draft's text for a text draft, of the returned `text` "
            "otherwise. 0 means no line."
        )
    )
    section: str | None
    message: str
    suggestion: str


_SECTION_HINT = {
    EXPERIENCES_SECTION: (
        "Commencez-la par « - » pour en faire une réalisation, ou par « ### » pour une expérience."
    ),
    FORMATION_SECTION: "Commencez-la par « - » pour en faire une formation.",
    COMPETENCES_SECTION: "Commencez-la par « - » pour en faire une compétence.",
    LOISIRS_SECTION: "Commencez-la par « - » pour en faire un loisir.",
}

_PERSONAL_DATA: dict[str, tuple[DiagnosticCode, str]] = {
    "email": ("personal_email", "Adresse e-mail détectée"),
    "phone": ("personal_phone", "Numéro de téléphone détecté"),
    "url": ("personal_url", "Adresse web de profil détectée"),
}


def _from_scan(line: ScannedLine, line_no: int) -> CvDiagnostic | None:
    section = line.section or None
    if line.problem == "unknown_section":
        return CvDiagnostic(
            code="unknown_section",
            level="info",
            line_no=line_no,
            section=section,
            message=(
                f"Section inconnue « {line.section} » : conservée telle quelle, "
                "ignorée par les flux."
            ),
            suggestion=(
                "Sections reconnues : Résumé, Expériences, Formation, Compétences, Loisirs "
                "(ou leurs équivalents anglais)."
            ),
        )
    if line.problem == "unrecognized_line":
        return CvDiagnostic(
            code="unrecognized_line",
            level="warning",
            line_no=line_no,
            section=section,
            message=f"Ligne non reconnue dans « {line.section} » : elle est ignorée.",
            suggestion=_SECTION_HINT[line.section],
        )
    if line.problem == "heading_outside":
        return CvDiagnostic(
            code="heading_outside",
            level="warning",
            line_no=line_no,
            section=section,
            message=(
                f"Titre de niveau 3 dans « {line.section} » : ignoré, seules les sections "
                "Expériences et Formation en ont."
            ),
            suggestion=(
                "Utilisez « - » pour une puce, ou déplacez ce titre sous Expériences ou Formation."
            ),
        )
    if line.problem == "orphan_bullet":
        return CvDiagnostic(
            code="orphan_bullet",
            level="warning",
            line_no=line_no,
            section=section,
            message="Réalisation placée avant toute expérience : elle ne sera rattachée à aucune.",
            suggestion="Ajoutez au-dessus un titre « ### Entreprise — Poste — dates ».",
        )
    if line.problem == "title_line":
        return CvDiagnostic(
            code="title_line",
            level="warning",
            line_no=line_no,
            section=section,
            message="Titre de premier niveau : il est ignoré.",
            suggestion="Retirez-le : votre nom est ajouté depuis l'identité, au rendu du document.",
        )
    if line.problem == "outside_section":
        return CvDiagnostic(
            code="outside_section",
            level="warning",
            line_no=line_no,
            section=section,
            message="Texte avant la première section : il est ignoré.",
            suggestion="Placez-le sous un titre de section, par exemple « ## Résumé ».",
        )
    if line.kind == "experience" and extract_comment(line.raw)[0].startswith(UNTITLED_EXPERIENCE):
        return CvDiagnostic(
            code="missing_title",
            level="warning",
            line_no=line_no,
            section=section,
            message="Expérience sans intitulé : ses réalisations ne sont rattachées à rien.",
            suggestion="Indiquez au moins l'entreprise, le poste ou les dates.",
        )
    return None


def _section_at(line_no: int, scanned: list[ScannedLine], first_line: int) -> str | None:
    section: str | None = None
    for line in scanned:
        if line.index + first_line > line_no:
            break
        if line.role == "section":
            section = line.section
    return section


def _front_matter_problem(text: str) -> CvDiagnostic | None:
    try:
        split_front_matter(text)
    except ValueError as exc:
        return CvDiagnostic(
            code="invalid_front_matter",
            level="error",
            line_no=1,
            section=None,
            message=str(exc).splitlines()[0].capitalize() + ".",
            suggestion=(
                "Corrigez le bloc entre les deux lignes « --- » (YAML, par exemple "
                "« lang: fr »), ou supprimez-le."
            ),
        )
    return None


def diagnose_cv(text: str) -> list[CvDiagnostic]:
    """Every diagnostic on a CV text; line numbers are those of the text as given."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    head = split_head(text)[1]
    first_line = head.count("\n") + 1
    lines = text[len(head) :].split("\n")
    scanned = scan_cv_body(lines)
    # A broken block reads as lines outside any section: one message is enough for it.
    problem = _front_matter_problem(text)
    found = (
        [problem]
        if problem
        else [
            diagnostic
            for line in scanned
            if (diagnostic := _from_scan(line, line.index + first_line)) is not None
        ]
    )
    found += [
        CvDiagnostic(
            code="duplicate_id",
            level="error",
            line_no=error.line_no,
            section=error.section,
            message=error.message.capitalize() + ".",
            suggestion="Retirez l'un des deux commentaires « id= » : l'enregistrement est bloqué.",
        )
        for error in parse_cv_markdown(text).errors
        if error.kind == "duplicate_id"
    ]
    for finding in find_personal_data(text):
        code, label = _PERSONAL_DATA[finding.kind]
        found.append(
            CvDiagnostic(
                code=code,
                level="warning",
                line_no=finding.line_no,
                section=_section_at(finding.line_no, scanned, first_line),
                message=f"{label} : « {finding.snippet} »",
                suggestion=(
                    "Retirez-la du CV : le CV est lu par le modèle, vos coordonnées sont "
                    "stockées à part et ajoutées au rendu du document."
                ),
            )
        )
    return sorted(found, key=lambda diagnostic: diagnostic.line_no)


def diagnose_fields(fields: CvFields) -> list[CvDiagnostic]:
    """What only the form can get wrong: a keyword that cannot be written is dropped."""
    found: list[CvDiagnostic] = []
    for number, experience in enumerate(fields.experiences, start=1):
        bad = split_tags(experience.tags)[1]
        if bad:
            found.append(
                CvDiagnostic(
                    code="invalid_tag",
                    level="warning",
                    line_no=0,
                    section=EXPERIENCES_SECTION,
                    message=f"Expérience n° {number} : mot-clé retiré ({', '.join(bad)}).",
                    suggestion="Un mot-clé commence par une lettre.",
                )
            )
    return found

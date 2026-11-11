import base64
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from jobingo.domain.cv_selection import CvSelection
from jobingo.domain.cv_template import CvManifest
from jobingo.domain.identity import Identity
from jobingo.render.pdf import render_pdf

TEMPLATE_DIR = Path(__file__).parent / "templates" / "panneau-lateral"

# Standard section headings: a recruiting tool scanning the PDF looks for these words,
# so they are not the template's to invent.
SECTION_LABELS = {
    "resume": "Résumé",
    "experiences": "Expérience",
    "projets": "Projets personnels",
    "formation": "Formation",
    "competences": "Compétences",
    "loisirs": "Loisirs",
}


@dataclass(frozen=True)
class RenderedCv:
    pdf: bytes
    pages: int


@cache
def load_manifest() -> CvManifest:
    manifest = yaml.safe_load((TEMPLATE_DIR / "manifest.yaml").read_text(encoding="utf-8"))
    return CvManifest.model_validate(manifest)


def document_title(identity: Identity) -> str:
    return f"CV — {identity.name}" if identity.name else "CV"


def render_cv(
    selection: CvSelection,
    identity: Identity,
    *,
    photo: bytes | None = None,
    template_dir: Path = TEMPLATE_DIR,
) -> RenderedCv:
    """Fill the template with the selection and the identity, then produce the PDF.

    The identity and the photo arrive here as parameters and are never part of the
    selection, so the selection can be stored, and later read by a model flow, without
    them. The photo is embedded only when its option is on.
    """
    # StrictUndefined: a renamed field must break the render loudly rather than silently
    # produce a CV with an empty section.
    environment = Environment(
        loader=FileSystemLoader(template_dir), undefined=StrictUndefined, autoescape=True
    )
    embedded = photo if photo and selection.options.photo else None
    html = environment.get_template("template.html").render(
        identity=identity,
        contact=identity.contact_entries(),
        selection=selection,
        labels=SECTION_LABELS,
        lang=selection.lang,
        doc_title=document_title(identity),
        options=selection.options,
        photo_uri=_photo_uri(embedded) if embedded else "",
    )
    css = (template_dir / "style.css").read_text(encoding="utf-8")
    pdf, pages = render_pdf(html, css, template_dir)
    return RenderedCv(pdf=pdf, pages=pages)


def _photo_uri(photo: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(photo).decode("ascii")

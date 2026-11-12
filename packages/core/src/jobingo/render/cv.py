import base64
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from jobingo.domain.chronology import chronology_key
from jobingo.domain.cv_selection import CvSelection
from jobingo.domain.cv_template import CvManifest
from jobingo.domain.identity import Identity
from jobingo.render.pdf import render_pdf

TEMPLATE_DIR = Path(__file__).parent / "templates" / "panneau-lateral"

# Standard section headings: a recruiting tool scanning the PDF looks for these words,
# so they are not the template's to invent.
SECTION_LABELS = {
    "resume": "Résumé",
    "experiences": "Expérience professionnelle",
    "projets": "Projets personnels",
    "formation": "Formation",
    "competences": "Compétences",
    "langues": "Langues",
    "loisirs": "Loisirs",
}


# The separator CV titles use between company, role and dates.
_TITLE_SEPARATOR = " — "


def title_and_dates(text: str) -> tuple[str, str]:
    """A title split before its dates, so the template can set them apart: « Nordlys —
    Ingénieur — 01/2022 – 08/2026 » gives (« Nordlys — Ingénieur », « 01/2022 – 08/2026
    »). A title whose last part states no date stays whole. The PDF's text is unchanged:
    the template prints the separator back."""
    head, separator, tail = text.rpartition(_TITLE_SEPARATOR)
    if not separator or not head.strip() or chronology_key(tail) is None:
        return text, ""
    return head, tail


@dataclass(frozen=True)
class RenderedCv:
    pdf: bytes
    pages: int
    # How full the last page is, 0 to 1; None when it could not be measured.
    fill: float | None = None


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
    html = _filled_template(selection, identity, photo, template_dir)
    css = (template_dir / "style.css").read_text(encoding="utf-8")
    rendered = render_pdf(html, css, template_dir)
    return RenderedCv(pdf=rendered.pdf, pages=rendered.pages, fill=rendered.fill)


def standalone_cv_html(
    selection: CvSelection,
    identity: Identity,
    *,
    photo: bytes | None = None,
    template_dir: Path = TEMPLATE_DIR,
) -> str:
    """The CV as one self-contained HTML file, for the user to adjust elsewhere (by hand,
    or with another assistant) before printing it: the stylesheet inlined, its fonts and
    the photo as `data:` URIs, nothing fetched. A few rules apart from the PDF's let a
    browser show the A4 sheet as WeasyPrint lays it out."""
    html = _filled_template(selection, identity, photo, template_dir)
    css = (template_dir / "style.css").read_text(encoding="utf-8")
    inlined = _FONT_URL.sub(lambda match: _font_uri(template_dir / match["path"]), css)
    style = f"<style>\n{inlined}\n{_BROWSER_CSS}</style>\n"
    return html.replace("</head>", style + "</head>", 1)


# What WeasyPrint does on the page box and a browser does not: the A4 sheet, its margins
# and the panel's dark background, painted here on the body.
_BROWSER_CSS = """/* For a browser, not the PDF engine: the A4 sheet and the panel background. */
html { background: #e5e5e5; }
body {
    position: relative;
    box-sizing: border-box;
    width: 210mm;
    min-height: 297mm;
    margin: 0 auto;
    padding: 9mm 0 8mm;
    background: #ffffff;
    print-color-adjust: exact;
    -webkit-print-color-adjust: exact;
}
body.with-panel {
    background: linear-gradient(to right, #ffffff calc(100% - 62mm), #333333 calc(100% - 62mm));
}
aside.panel { top: 9mm; }
@media print {
    @page { margin: 0; }
    html { background: none; }
}
"""
_FONT_URL = re.compile(r'url\("(?P<path>fonts/[^"]+\.woff)"\)')


def _font_uri(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f'url("data:font/woff;base64,{data}")'


def _filled_template(
    selection: CvSelection, identity: Identity, photo: bytes | None, template_dir: Path
) -> str:
    # StrictUndefined: a renamed field must break the render loudly rather than silently
    # produce a CV with an empty section.
    environment = Environment(
        loader=FileSystemLoader(template_dir), undefined=StrictUndefined, autoescape=True
    )
    embedded = photo if photo and selection.options.photo else None
    return environment.get_template("template.html").render(
        identity=identity,
        contact=identity.contact_entries(),
        selection=selection,
        labels=SECTION_LABELS,
        lang=selection.lang,
        doc_title=document_title(identity),
        options=selection.options,
        photo_uri=_photo_uri(embedded) if embedded else "",
        title_and_dates=title_and_dates,
    )


def _photo_uri(photo: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(photo).decode("ascii")

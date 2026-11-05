"""Render a CV to PDF for real, then read the PDF's own text back."""

import io
from pathlib import Path
from typing import Any, cast

import pytest
from pypdf import PdfReader
from tests.images import jpeg_bytes

from jobingo.domain.cv_selection import DEFAULT_OPTIONS, CvOptions, CvSelection, build_selection
from jobingo.domain.identity import Identity
from jobingo.domain.profile import Profile, parse_cv_markdown
from jobingo.render.cv import TEMPLATE_DIR, load_manifest, render_cv
from jobingo.render.pdf import engine_available
from jobingo.render.verify import PdfProblem, compact, extract_pdf_text, verify_cv_pdf

pytestmark = pytest.mark.skipif(
    not engine_available(),
    reason="WeasyPrint's system libraries are missing (brew install pango)",
)

FIXTURE = (Path(__file__).parent / "fixtures" / "cv.fr.md").read_text(encoding="utf-8")
WITH_HOBBIES = FIXTURE + "\n## Loisirs\n\n- Escalade <!-- id=hobby-1 -->\n"
ALEX = Identity(
    name="Alex Moreau",
    email="alex.moreau@example.org",
    phone="06 00 00 00 00",
    address="12 rue des Lilas, 69003 Lyon",
    linkedin="linkedin.com/in/alex-moreau",
    github="github.com/alex-moreau",
)


def _selection(
    profile: Profile,
    excluded: set[str] | None = None,
    options: CvOptions = DEFAULT_OPTIONS,
) -> CvSelection:
    return build_selection(
        profile, excluded or set(), options, template="panneau-lateral", lang="fr"
    )


def _options(**changes: bool) -> CvOptions:
    return DEFAULT_OPTIONS.model_copy(update=changes)


def _images_on_first_page(pdf: bytes) -> int:
    return len(PdfReader(io.BytesIO(pdf)).pages[0].images)


@pytest.mark.parametrize("panel", [True, False])
def test_every_selected_item_is_in_the_pdf_in_order(panel: bool):
    selection = _selection(
        parse_cv_markdown(WITH_HOBBIES), options=_options(panneau_competences=panel)
    )

    rendered = render_cv(selection, ALEX)

    assert verify_cv_pdf(rendered.pdf, selection) == []
    assert rendered.pages == 1


def test_an_unselected_item_is_absent():
    selection = _selection(
        parse_cv_markdown(FIXTURE), {"nordlys-03", "skill-kubernetes", "formation-02"}
    )

    text = compact(extract_pdf_text(render_cv(selection, ALEX).pdf))

    assert compact("API de facturation") not in text
    assert "Kubernetes" not in text
    assert compact("Certification AWS") not in text
    assert compact("Migration de 120 tâches") in text


def test_a_bullet_leaves_with_its_experience():
    selection = _selection(parse_cv_markdown(FIXTURE), {"batiflux"})

    text = compact(extract_pdf_text(render_cv(selection, ALEX).pdf))

    assert "Batiflux" not in text
    assert compact("Refonte du module de devis") not in text


def test_the_panel_holds_contact_and_skills_only_when_on():
    profile = parse_cv_markdown(FIXTURE)
    with_panel = render_cv(_selection(profile), ALEX).pdf
    without = render_cv(_selection(profile, options=_options(panneau_competences=False)), ALEX).pdf

    def order(pdf: bytes) -> tuple[int, int, int]:
        text = compact(extract_pdf_text(pdf))
        return text.index("alex.moreau@"), text.index("Expérience"), text.index("Compétences")

    # The panel's text follows the main column; without it, contact is in the header.
    contact, experience, skills = order(with_panel)
    assert experience < contact and experience < skills
    contact, experience, skills = order(without)
    assert contact < experience < skills


def test_the_panel_stays_the_first_block_of_the_document():
    template = (TEMPLATE_DIR / "template.html").read_text(encoding="utf-8")
    assert template.index('<aside class="panel">') < template.index("<main>")


def test_the_stylesheet_keeps_the_reading_order_and_the_text_whole():
    css = (TEMPLATE_DIR / "style.css").read_text(encoding="utf-8")
    declarations = "\n".join(line for line in css.splitlines() if line.rstrip().endswith(";"))
    assert "position: relative" not in declarations
    assert "text-transform" not in declarations
    assert "hyphens: none" in declarations


@pytest.mark.parametrize("panel", [True, False])
def test_the_photo_is_embedded_only_when_its_option_is_on(panel: bool):
    profile = parse_cv_markdown(FIXTURE)
    photo = jpeg_bytes()

    off = _selection(profile, options=_options(photo=False, panneau_competences=panel))
    on = _selection(profile, options=_options(photo=True, panneau_competences=panel))

    assert _images_on_first_page(render_cv(off, ALEX, photo=photo).pdf) == 0
    assert _images_on_first_page(render_cv(on, ALEX, photo=photo).pdf) == 1


@pytest.mark.parametrize("panel", [True, False])
def test_hobbies_are_printed_only_when_their_option_is_on(panel: bool):
    profile = parse_cv_markdown(WITH_HOBBIES)

    def text(loisirs: bool) -> str:
        options = _options(loisirs=loisirs, panneau_competences=panel)
        return extract_pdf_text(render_cv(_selection(profile, options=options), ALEX).pdf)

    assert "Escalade" in text(True) and "Loisirs" in text(True)
    assert "Escalade" not in text(False) and "Loisirs" not in text(False)


def test_an_empty_identity_leaves_nothing_behind():
    selection = _selection(parse_cv_markdown(FIXTURE))

    rendered = render_cv(selection, Identity())

    assert verify_cv_pdf(rendered.pdf, selection) == []
    metadata = PdfReader(io.BytesIO(rendered.pdf)).metadata
    assert metadata is not None
    assert metadata.title == "CV"
    assert not metadata.author


def test_identity_is_injected_at_render_time_only():
    selection = _selection(parse_cv_markdown(FIXTURE))

    text = compact(extract_pdf_text(render_cv(selection, ALEX).pdf))

    for value in (ALEX.name, ALEX.email, ALEX.phone, ALEX.linkedin):
        assert compact(value) in text
    stored = selection.model_dump_json()
    for value in (ALEX.name, ALEX.email, ALEX.phone, ALEX.linkedin):
        assert value not in stored


def test_the_metadata_names_the_document():
    rendered = render_cv(_selection(parse_cv_markdown(FIXTURE)), ALEX)

    metadata = PdfReader(io.BytesIO(rendered.pdf)).metadata

    assert metadata is not None
    assert metadata.title == "CV — Alex Moreau"
    assert metadata.author == "Alex Moreau"


def test_standard_section_headings_are_present():
    text = extract_pdf_text(render_cv(_selection(parse_cv_markdown(WITH_HOBBIES)), ALEX).pdf)
    for label in ("Expérience", "Formation", "Compétences", "Loisirs"):
        assert label in text


def _long_cv() -> str:
    jobs = "\n\n".join(
        f"### Société {n} — Développeur — 01/20{n:02d} – 12/20{n:02d} <!-- id=job-{n} -->\n\n"
        + "\n".join(
            f"- Réalisation numéro {b} de la société {n} <!-- id=job-{n}-{b} -->" for b in range(8)
        )
        for n in range(10)
    )
    return f"## Expériences\n\n{jobs}\n"


@pytest.mark.parametrize("panel", [True, False])
def test_a_long_cv_runs_over_one_page_and_is_counted(panel: bool):
    selection = _selection(
        parse_cv_markdown(_long_cv()), options=_options(panneau_competences=panel)
    )

    rendered = render_cv(selection, ALEX)

    assert rendered.pages > 1
    assert len(PdfReader(io.BytesIO(rendered.pdf)).pages) == rendered.pages
    assert verify_cv_pdf(rendered.pdf, selection) == []


def test_a_panel_longer_than_its_page_is_cut_and_verify_says_so():
    """The panel is absolutely positioned: what runs past the page is lost, and the page
    count stays at 1. This pins the behaviour the screen's warning relies on."""
    skills = "\n".join(f"- Compétence numéro {n} <!-- id=sk{n} -->" for n in range(70))
    selection = _selection(parse_cv_markdown(f"## Compétences\n\n{skills}\n"))

    rendered = render_cv(selection, ALEX)

    assert rendered.pages == 1
    missing = [
        p.subject for p in verify_cv_pdf(rendered.pdf, selection) if p.kind == "item_missing"
    ]
    assert missing and missing[-1] == "sk69"


def test_verify_reports_an_item_missing_from_the_pdf():
    """The check has to be able to fail, or it proves nothing."""
    selection = _selection(parse_cv_markdown(FIXTURE))
    rendered = render_cv(selection, ALEX)

    tampered = selection.model_copy(deep=True)
    tampered.competences.append(
        tampered.competences[0].model_copy(update={"id": "fantome", "text": "Rust et Haskell"})
    )

    assert verify_cv_pdf(rendered.pdf, tampered) == [PdfProblem("item_missing", "fantome")]


def test_verify_reports_items_out_of_order():
    selection = _selection(parse_cv_markdown(FIXTURE))
    rendered = render_cv(selection, ALEX)

    shuffled = selection.model_copy(deep=True)
    shuffled.competences.reverse()

    kinds = {problem.kind for problem in verify_cv_pdf(rendered.pdf, shuffled)}
    assert kinds == {"item_out_of_sequence"}


def test_the_manifest_declares_the_options_and_one_page():
    manifest = load_manifest()
    assert manifest.max_pages == 1
    assert set(manifest.options) == {"photo", "panneau_competences", "loisirs"}


def test_the_font_is_embedded_so_the_layout_does_not_depend_on_the_machine():
    rendered = render_cv(_selection(parse_cv_markdown(FIXTURE)), ALEX)

    fonts: set[str] = set()
    for page in PdfReader(io.BytesIO(rendered.pdf)).pages:
        resources = cast(dict[str, Any], page["/Resources"])
        for font in cast(dict[str, Any], resources["/Font"]).values():
            fonts.add(str(font["/BaseFont"]))
    assert fonts
    assert all("Lato" in font for font in fonts), fonts


def test_a_summary_left_out_is_not_in_the_pdf():
    profile = parse_cv_markdown(FIXTURE)
    summary = next(item for item in profile.items if item.kind == "resume")

    selection = _selection(profile, excluded={summary.id})
    text = compact(extract_pdf_text(render_cv(selection, ALEX).pdf))

    assert selection.resume is None
    assert compact(summary.text) not in text

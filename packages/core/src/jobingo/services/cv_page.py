"""What goes on the page, kept per user, and its render to PDF."""

import logging
import re
from dataclasses import dataclass

from jobingo.db import Conn
from jobingo.domain.cv_document import CvLang
from jobingo.domain.cv_selection import (
    DEFAULT_OPTIONS,
    CvOptions,
    CvPage,
    CvSelection,
    OptionBlockers,
    SelectionChoice,
    build_selection,
    has_hobbies,
    known_ids,
    option_blockers,
    page_of,
)
from jobingo.domain.identity import Identity
from jobingo.domain.profile import Profile, parse_cv_markdown
from jobingo.domain.text import fold
from jobingo.render.cv import RenderedCv, load_manifest, render_cv
from jobingo.render.pdf import PdfEngineUnavailable
from jobingo.render.verify import verify_cv_pdf
from jobingo.services.cv import load_cv
from jobingo.services.identity import has_photo, load_identity, load_photo

log = logging.getLogger(__name__)


class OptionUnavailableError(Exception):
    """An option was asked for that cannot be on. The message is shown to the user."""


class CvRenderError(Exception):
    """The PDF could not be produced. The message is shown to the user."""


@dataclass(frozen=True)
class CvPdf:
    rendered: RenderedCv
    filename: str
    missing_items: int  # selected but not in the PDF: a side panel longer than its page


def _load_profile(conn: Conn, user_id: int, lang: CvLang) -> Profile:
    stored = load_cv(conn, user_id, lang)
    return parse_cv_markdown(stored.content if stored else "")


def _load_choice(conn: Conn, user_id: int, lang: CvLang) -> SelectionChoice:
    row = conn.execute(
        """
        SELECT excluded_ids, photo, panneau_competences, loisirs
        FROM cv_selections
        WHERE user_id = %s AND lang = %s
        """,
        (user_id, lang),
    ).fetchone()
    if row is None:
        return SelectionChoice(excluded_ids=[], options=DEFAULT_OPTIONS)
    options = CvOptions(
        photo=row["photo"],
        panneau_competences=row["panneau_competences"],
        loisirs=row["loisirs"],
    )
    return SelectionChoice(excluded_ids=row["excluded_ids"], options=options)


def _blockers(conn: Conn, user_id: int, profile: Profile) -> OptionBlockers:
    return option_blockers(
        load_manifest(), has_photo=has_photo(conn, user_id), has_hobbies=has_hobbies(profile)
    )


def load_page(conn: Conn, user_id: int, lang: CvLang) -> CvPage:
    profile = _load_profile(conn, user_id, lang)
    choice = _load_choice(conn, user_id, lang)
    blockers = _blockers(conn, user_id, profile)
    return page_of(profile, set(choice.excluded_ids), choice.options, blockers, load_manifest())


def save_choice(conn: Conn, user_id: int, lang: CvLang, choice: SelectionChoice) -> CvPage:
    """Raises `OptionUnavailableError`."""
    profile = _load_profile(conn, user_id, lang)
    blockers = _blockers(conn, user_id, profile)
    blocked = blockers.first_blocking(choice.options)
    if blocked:
        raise OptionUnavailableError(blocked)
    options = choice.options.kept_where_blocked(_load_choice(conn, user_id, lang).options, blockers)
    conn.execute(
        """
        INSERT INTO cv_selections (user_id, lang, excluded_ids, photo, panneau_competences, loisirs)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, lang) DO UPDATE SET
            excluded_ids = EXCLUDED.excluded_ids,
            photo = EXCLUDED.photo,
            panneau_competences = EXCLUDED.panneau_competences,
            loisirs = EXCLUDED.loisirs,
            updated_at = now()
        """,
        (
            user_id,
            lang,
            known_ids(profile, set(choice.excluded_ids)),
            options.photo,
            options.panneau_competences,
            options.loisirs,
        ),
    )
    return load_page(conn, user_id, lang)


def _filename(identity: Identity) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", fold(identity.name)).strip("-")
    return f"cv-{slug}.pdf" if slug else "cv.pdf"


def page_options(conn: Conn, user_id: int, lang: CvLang) -> tuple[CvOptions, OptionBlockers]:
    """The options the user chose on the CV page, as they apply now, and what blocks
    each one."""
    profile = _load_profile(conn, user_id, lang)
    blockers = _blockers(conn, user_id, profile)
    return _load_choice(conn, user_id, lang).options.clamped_to(blockers), blockers


def render_page(conn: Conn, user_id: int, lang: CvLang) -> CvPdf:
    """The PDF of the stored selection. Raises `CvRenderError`."""
    manifest = load_manifest()
    profile = _load_profile(conn, user_id, lang)
    choice = _load_choice(conn, user_id, lang)
    options = choice.options.clamped_to(_blockers(conn, user_id, profile))
    selection = build_selection(
        profile, set(choice.excluded_ids), options, template=manifest.name, lang=lang
    )
    return render_selection(conn, user_id, selection)


def render_selection(conn: Conn, user_id: int, selection: CvSelection) -> CvPdf:
    """The PDF of `selection`, with the identity put back. Raises `CvRenderError`.

    Logs carry no message from the render, which could quote the document's content.
    """
    identity = load_identity(conn, user_id)
    photo = load_photo(conn, user_id) if selection.options.photo else None
    try:
        rendered = render_cv(selection, identity, photo=photo)
        problems = verify_cv_pdf(rendered.pdf, selection)
    except PdfEngineUnavailable as error:
        log.error("CV render: the PDF engine is unavailable")
        raise CvRenderError(str(error)) from None
    except Exception as error:
        log.error("CV render failed: %s", type(error).__name__)
        raise CvRenderError("Le PDF n'a pas pu être produit.") from None
    missing = sum(problem.kind == "item_missing" for problem in problems)
    return CvPdf(rendered=rendered, filename=_filename(identity), missing_items=missing)

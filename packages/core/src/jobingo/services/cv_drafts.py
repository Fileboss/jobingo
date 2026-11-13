"""CVs adapted to an application: proposed by the model, checked by code, settled by the
user. They are made from the application, from its offer when it has one.

Nothing here writes the source CV: a draft holds ids and texts, and the CV stays the
user's own words (`tests/test_architecture.py`).
"""

import logging
from collections.abc import Callable
from typing import Any

from psycopg.types.json import Jsonb

from jobingo.db import Conn
from jobingo.domain.cv_document import CvLang
from jobingo.domain.cv_draft import (
    DraftChoices,
    DraftSummary,
    DraftView,
    OfferInput,
    cleaned_choices,
    draft_items,
    draft_selection,
    gone_items,
    initial_choices,
)
from jobingo.domain.cv_proposal import TailoredCv
from jobingo.domain.cv_selection import CvOptions, CvSelection
from jobingo.domain.fitting import MIN_FILL, PageMeasure
from jobingo.domain.profile import Profile, parse_cv_markdown
from jobingo.llm.client import LLMClient
from jobingo.llm.journal import Budget
from jobingo.logs import event
from jobingo.render.cv import load_manifest
from jobingo.services.applications import get_application
from jobingo.services.cv import load_cv
from jobingo.services.cv_page import (
    CvHtml,
    CvPdf,
    CvRenderError,
    OptionUnavailableError,
    html_of_selection,
    page_options,
    render_selection,
)
from jobingo.services.cv_proposal import OfferText, RankedProposal, propose_cv
from jobingo.services.offers import get_offer

log = logging.getLogger(__name__)

_COLUMNS = """
    id, lang, offer_id, application_id, offer_title, offer_company, offer_description,
    llm_call_id, proposal, choices, created_at, updated_at
"""


def _profile(conn: Conn, user_id: int, lang: CvLang) -> Profile:
    stored = load_cv(conn, user_id, lang)
    return parse_cv_markdown(stored.content if stored else "")


def create_draft(
    conn: Conn,
    client: LLMClient,
    budget: Budget,
    user_id: int,
    lang: CvLang,
    offer: OfferInput,
    *,
    application_id: int,
    offer_id: int | None = None,
) -> DraftView:
    """Ask for a proposal that fits the page and store it with the starting choices:
    what the model kept, with the rewrites code accepted, and the options of the CV page.

    Raises what `propose_cv` raises on the first call, before anything is stored.
    """
    options, _ = page_options(conn, user_id, lang)
    tailored, call_id = _propose_on_the_page(
        conn,
        client,
        budget,
        user_id,
        lang,
        OfferText(title=offer.title, company=offer.company, description=offer.description),
        options,
    )
    row = conn.execute(
        """
        INSERT INTO cv_drafts (user_id, lang, offer_id, application_id, offer_title,
            offer_company, offer_description, llm_call_id, proposal, choices)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            user_id,
            lang,
            offer_id,
            application_id,
            offer.title,
            offer.company,
            offer.description,
            call_id,
            Jsonb(tailored.model_dump(mode="json")),
            Jsonb(initial_choices(tailored, options).model_dump(mode="json")),
        ),
    ).fetchone()
    assert row is not None
    event(
        log,
        "cv.draft_created",
        user_id=user_id,
        llm_call_id=call_id,
        draft_id=row["id"],
        application_id=application_id,
    )
    view = load_draft(conn, user_id, row["id"])
    assert view is not None
    return view


# Renders to find how much of a ranking fits, the whole of it included: a binary search
# over up to some hundred elements.
MAX_FIT_RENDERS = 8


def _propose_on_the_page(
    conn: Conn,
    client: LLMClient,
    budget: Budget,
    user_id: int,
    lang: CvLang,
    offer: OfferText,
    options: CvOptions,
) -> tuple[TailoredCv, int]:
    """The model's ranking for `offer`, taken as far as the page holds."""
    ranked, call_id = propose_cv(
        conn, client, budget, user_id, lang, offer, hobbies=options.loisirs
    )
    tailored = fit_ranking(conn, user_id, lang, ranked, options)
    event(
        log,
        "cv.page_fitted",
        user_id=user_id,
        llm_call_id=call_id,
        ranked=ranked.size,
        taken=len(tailored.kept_items()),
    )
    return tailored, call_id


def fit_ranking(
    conn: Conn, user_id: int, lang: CvLang, ranked: RankedProposal, options: CvOptions
) -> TailoredCv:
    """The model's ranking taken as far as the page holds, found by binary searches over
    real renders, which are not stored. The page has two areas that fill apart: the side
    panel, cut at the bottom of its page with no page added, and the main column, which
    flows onto a second page. So the panel is fitted first, its last elements left out
    (hobbies, then the least useful skills), then the column takes the longest head of
    the ranking that keeps to one page. Code adds nothing the model did not rank. A page
    under `MIN_FILL` gets a warning saying why. The eval fits with it too."""

    def measure(n: int, side: int) -> PageMeasure | None:
        return measure_page(conn, user_id, lang, ranked.at(n, side=side), options)

    side, _ = _longest(ranked.side_size, lambda k: measure(0, k), lambda p: p.panel_runs_over)
    chosen, page = _longest(ranked.size, lambda n: measure(n, side), lambda p: p.column_runs_over)
    tailored = ranked.at(chosen, side=side)
    if page is None or page.fill is None:
        return tailored
    percent = round(100 * page.fill)
    if page.runs_over:
        return _warned(tailored, "Le CV dépasse la page : décochez des éléments pour qu'il tienne.")
    if page.fill < MIN_FILL and chosen == ranked.size:
        return _warned(
            tailored,
            f"La page n'est remplie qu'à {percent} % : le modèle n'a classé que "
            f"{ranked.size} éléments pour cette offre. Cochez-en d'autres pour la compléter.",
        )
    if page.fill < MIN_FILL:
        return _warned(
            tailored,
            f"La page n'est remplie qu'à {percent} % : l'élément suivant du classement "
            "ne tenait pas. Cochez-en d'autres pour la compléter.",
        )
    return tailored


def _longest(
    size: int,
    measure: Callable[[int], PageMeasure | None],
    too_much: Callable[[PageMeasure], bool],
) -> tuple[int, PageMeasure | None]:
    """The largest count up to `size` whose page is not `too_much`, and its measure, by
    a binary search: one more element can only make it worse. Zero is assumed to fit.
    Without a measure (no PDF engine), everything is kept."""
    whole = measure(size)
    if whole is None or not too_much(whole):
        return size, whole
    low, high = 0, size
    seen: dict[int, PageMeasure] = {}
    renders = 1
    while high - low > 1 and renders < MAX_FIT_RENDERS:
        middle = (low + high) // 2
        measured = measure(middle)
        renders += 1
        if measured is None:
            break
        seen[middle] = measured
        if too_much(measured):
            high = middle
        else:
            low = middle
    return low, seen.get(low) or measure(low)


def measure_page(
    conn: Conn, user_id: int, lang: CvLang, tailored: TailoredCv, options: CvOptions
) -> PageMeasure | None:
    """The proposal's page, as the draft will first show it. None when it cannot be
    rendered here: the draft's own render says so again. The eval measures with it too."""
    profile = _profile(conn, user_id, lang)
    manifest = load_manifest()
    selection = draft_selection(
        profile,
        tailored,
        cleaned_choices(initial_choices(tailored, options), profile),
        template=manifest.name,
        lang=lang,
    )
    try:
        pdf = render_selection(conn, user_id, selection)
    except CvRenderError:
        return None
    return PageMeasure(
        pages=pdf.rendered.pages,
        missing_items=pdf.missing_items,
        fill=pdf.rendered.fill,
        max_pages=manifest.max_pages,
    )


def _warned(tailored: TailoredCv, warning: str) -> TailoredCv:
    return tailored.model_copy(update={"warnings": [*tailored.warnings, warning]})


def target_of(
    conn: Conn, user_id: int, application_id: int
) -> tuple[OfferInput, int | None] | None:
    """What the CV is adapted to: the application's offer, or for a spontaneous
    application what is known of it, the role, the company and the notes on it. None:
    no such application."""
    application = get_application(conn, user_id, application_id)
    if application is None:
        return None
    offer = get_offer(conn, user_id, application.offer_id) if application.offer_id else None
    if offer is not None:
        # A title-only offer is still something to adapt to.
        description = offer.description_md or offer.title
        return OfferInput(
            title=offer.title, company=offer.company_name, description=description
        ), offer.id
    lines = [f"Candidature spontanée, sans annonce : poste visé « {application.title} »."]
    if application.company_name:
        lines.append(f"Entreprise : {application.company_name}.")
    if application.company_notes.strip():
        lines.append(f"Ce que la personne sait de l'entreprise :\n{application.company_notes}")
    return OfferInput(
        title=application.title,
        company=application.company_name,
        description="\n\n".join(lines)[:20_000],
    ), None


def create_draft_for_application(
    conn: Conn,
    client: LLMClient,
    budget: Budget,
    user_id: int,
    lang: CvLang,
    application_id: int,
) -> DraftView | None:
    """`create_draft` for an application. None when there is no such application."""
    target = target_of(conn, user_id, application_id)
    if target is None:
        return None
    offer, offer_id = target
    return create_draft(
        conn, client, budget, user_id, lang, offer, application_id=application_id, offer_id=offer_id
    )


def list_drafts(conn: Conn, user_id: int, application_id: int) -> list[DraftSummary]:
    """The application's adapted CVs, newest first."""
    rows = conn.execute(
        """
        SELECT id, offer_id, application_id, offer_title, offer_company, llm_call_id,
            created_at, updated_at
        FROM cv_drafts
        WHERE user_id = %s AND application_id = %s
        ORDER BY created_at DESC, id DESC
        """,
        (user_id, application_id),
    )
    return [DraftSummary.model_validate(row) for row in rows]


def _row(conn: Conn, user_id: int, draft_id: int) -> dict[str, Any] | None:
    return conn.execute(
        f"SELECT {_COLUMNS} FROM cv_drafts WHERE user_id = %s AND id = %s",  # nosec B608
        (user_id, draft_id),
    ).fetchone()


def load_draft(conn: Conn, user_id: int, draft_id: int) -> DraftView | None:
    row = _row(conn, user_id, draft_id)
    if row is None:
        return None
    lang: CvLang = row["lang"]
    profile = _profile(conn, user_id, lang)
    tailored = TailoredCv.model_validate(row["proposal"])
    choices = cleaned_choices(DraftChoices.model_validate(row["choices"]), profile)
    _, blockers = page_options(conn, user_id, lang)
    sections = draft_items(profile, tailored, choices)
    return DraftView(
        id=row["id"],
        lang=lang,
        offer_id=row["offer_id"],
        application_id=row["application_id"],
        offer=OfferInput(
            title=row["offer_title"],
            company=row["offer_company"],
            description=row["offer_description"],
        ),
        llm_call_id=row["llm_call_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        **dict(sections),
        options=choices.options.clamped_to(blockers),
        option_blockers=blockers,
        warnings=tailored.warnings,
        gone=gone_items(profile, tailored),
        max_pages=load_manifest().max_pages,
    )


def save_choices(
    conn: Conn, user_id: int, draft_id: int, choices: DraftChoices
) -> DraftView | None:
    """None when there is no such draft. Raises `OptionUnavailableError`."""
    row = _row(conn, user_id, draft_id)
    if row is None:
        return None
    lang: CvLang = row["lang"]
    _, blockers = page_options(conn, user_id, lang)
    blocked = blockers.first_blocking(choices.options)
    if blocked:
        raise OptionUnavailableError(blocked)
    cleaned = cleaned_choices(choices, _profile(conn, user_id, lang))
    conn.execute(
        "UPDATE cv_drafts SET choices = %s, updated_at = now() WHERE user_id = %s AND id = %s",
        (Jsonb(cleaned.model_dump(mode="json")), user_id, draft_id),
    )
    return load_draft(conn, user_id, draft_id)


def _settled_selection(conn: Conn, user_id: int, row: dict[str, Any]) -> CvSelection:
    """The draft's page as the user left it."""
    lang: CvLang = row["lang"]
    profile = _profile(conn, user_id, lang)
    _, blockers = page_options(conn, user_id, lang)
    choices = cleaned_choices(DraftChoices.model_validate(row["choices"]), profile)
    choices = choices.model_copy(update={"options": choices.options.clamped_to(blockers)})
    return draft_selection(
        profile,
        TailoredCv.model_validate(row["proposal"]),
        choices,
        template=load_manifest().name,
        lang=lang,
    )


def render_draft(conn: Conn, user_id: int, draft_id: int) -> CvPdf | None:
    """The PDF of the draft as the user left it. None when there is no such draft.
    Raises `CvRenderError`."""
    row = _row(conn, user_id, draft_id)
    if row is None:
        return None
    return render_selection(conn, user_id, _settled_selection(conn, user_id, row))


def draft_html(conn: Conn, user_id: int, draft_id: int) -> CvHtml | None:
    """The draft as the user left it, as one self-contained HTML file. None when there
    is no such draft."""
    row = _row(conn, user_id, draft_id)
    if row is None:
        return None
    return html_of_selection(conn, user_id, _settled_selection(conn, user_id, row))

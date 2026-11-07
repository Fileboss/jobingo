"""CVs adapted to an offer: proposed by the model, checked by code, settled by the user.

Nothing here writes the source CV: a draft holds ids and texts, and the CV stays the
user's own words (`tests/test_architecture.py`).
"""

import logging
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
from jobingo.domain.profile import Profile, parse_cv_markdown
from jobingo.llm.client import LLMClient
from jobingo.llm.journal import Budget
from jobingo.logs import event
from jobingo.render.cv import load_manifest
from jobingo.services.cv import load_cv
from jobingo.services.cv_page import CvPdf, OptionUnavailableError, page_options, render_selection
from jobingo.services.cv_proposal import OfferText, propose_cv
from jobingo.services.offers import get_offer

log = logging.getLogger(__name__)

_COLUMNS = """
    id, lang, offer_id, offer_title, offer_company, offer_description, llm_call_id, proposal,
    choices, created_at, updated_at
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
    offer_id: int | None = None,
) -> DraftView:
    """Ask for a proposal and store it with the starting choices: what the model kept,
    with the rewrites code accepted, and the options of the CV page.

    Raises what `propose_cv` raises, before anything is stored.
    """
    options, _ = page_options(conn, user_id, lang)
    tailored, call_id = propose_cv(
        conn,
        client,
        budget,
        user_id,
        lang,
        OfferText(title=offer.title, company=offer.company, description=offer.description),
        hobbies=options.loisirs,
    )
    row = conn.execute(
        """
        INSERT INTO cv_drafts (user_id, lang, offer_id, offer_title, offer_company,
            offer_description, llm_call_id, proposal, choices)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            user_id,
            lang,
            offer_id,
            offer.title,
            offer.company,
            offer.description,
            call_id,
            Jsonb(tailored.model_dump(mode="json")),
            Jsonb(initial_choices(tailored, options).model_dump(mode="json")),
        ),
    ).fetchone()
    assert row is not None
    event(log, "cv.draft_created", user_id=user_id, llm_call_id=call_id, draft_id=row["id"])
    view = load_draft(conn, user_id, row["id"])
    assert view is not None
    return view


def create_draft_for_offer(
    conn: Conn,
    client: LLMClient,
    budget: Budget,
    user_id: int,
    lang: CvLang,
    offer_id: int,
) -> DraftView | None:
    """`create_draft` on a stored offer. None when there is no such offer."""
    offer = get_offer(conn, user_id, offer_id)
    if offer is None:
        return None
    text = OfferInput(
        title=offer.title,
        company=offer.company_name,
        # A title-only offer is still something to adapt to.
        description=offer.description_md or offer.title,
    )
    return create_draft(conn, client, budget, user_id, lang, text, offer_id=offer_id)


def list_drafts(conn: Conn, user_id: int, *, offer_id: int | None = None) -> list[DraftSummary]:
    """Newest first; only those adapted to `offer_id` when it is given."""
    rows = conn.execute(
        """
        SELECT id, offer_id, offer_title, offer_company, llm_call_id, created_at, updated_at
        FROM cv_drafts
        WHERE user_id = %s AND (%s::bigint IS NULL OR offer_id = %s)
        ORDER BY created_at DESC, id DESC
        """,
        (user_id, offer_id, offer_id),
    )
    return [DraftSummary.model_validate(row) for row in rows]


def _row(conn: Conn, user_id: int, draft_id: int) -> dict[str, Any] | None:
    return conn.execute(
        f"SELECT {_COLUMNS} FROM cv_drafts WHERE user_id = %s AND id = %s",
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
    resume, experiences, formation, competences, loisirs = draft_items(profile, tailored, choices)
    return DraftView(
        id=row["id"],
        lang=lang,
        offer_id=row["offer_id"],
        offer=OfferInput(
            title=row["offer_title"],
            company=row["offer_company"],
            description=row["offer_description"],
        ),
        llm_call_id=row["llm_call_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        resume=resume,
        experiences=experiences,
        formation=formation,
        competences=competences,
        loisirs=loisirs,
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


def render_draft(conn: Conn, user_id: int, draft_id: int) -> CvPdf | None:
    """The PDF of the draft as the user left it. None when there is no such draft.
    Raises `CvRenderError`."""
    row = _row(conn, user_id, draft_id)
    if row is None:
        return None
    lang: CvLang = row["lang"]
    profile = _profile(conn, user_id, lang)
    _, blockers = page_options(conn, user_id, lang)
    choices = cleaned_choices(DraftChoices.model_validate(row["choices"]), profile)
    choices = choices.model_copy(update={"options": choices.options.clamped_to(blockers)})
    selection = draft_selection(
        profile,
        TailoredCv.model_validate(row["proposal"]),
        choices,
        template=load_manifest().name,
        lang=lang,
    )
    return render_selection(conn, user_id, selection)

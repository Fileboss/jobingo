"""Cover letters: drafted by the model slot by slot, checked by code, settled by the user,
rendered with the identity put back."""

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from jobingo.db import Conn
from jobingo.domain.letter import (
    LetterDraft,
    LetterSources,
    build_letter_draft,
    letter_problems,
)
from jobingo.domain.personal_data import find_personal_data
from jobingo.domain.profile import parse_cv_markdown
from jobingo.domain.style import StyleGuide
from jobingo.domain.text import fold
from jobingo.domain.text_checks import count_words
from jobingo.llm.client import LLMClient
from jobingo.llm.journal import Budget, run_task
from jobingo.llm.tasks.draft_letter import (
    DRAFT_LETTER_TASK,
    AchievementInput,
    DraftLetterInput,
    LetterSlotInput,
)
from jobingo.logs import event
from jobingo.render.letter import load_letter_manifest, render_letter
from jobingo.render.pdf import PdfEngineUnavailable
from jobingo.services.cv import load_cv
from jobingo.services.cv_drafts import list_drafts, load_draft
from jobingo.services.identity import load_identity, redaction_values
from jobingo.services.offers import get_offer

log = logging.getLogger(__name__)


class LetterNotPossibleError(Exception):
    """Nothing to write from, or contact details in the CV. Shown to the user."""


class LetterRenderError(Exception):
    """The PDF could not be produced. Shown to the user."""


class SlotView(BaseModel):
    name: str
    max_words: int
    text: str  # the letter's text now
    words: int
    # What the model did with this slot.
    proposed: str
    rejected_reason: str
    unsourced_names: list[str]


class LetterSummary(BaseModel):
    id: int
    application_id: int
    llm_call_id: int | None
    created_at: datetime
    updated_at: datetime


class LetterView(LetterSummary):
    application_title: str
    company_name: str
    recipient: str
    slots: list[SlotView]
    cited_ids: list[str]
    warnings: list[str]
    # What keeps the letter from being downloaded.
    problems: list[str]
    max_pages: int


class LetterTexts(BaseModel):
    texts: dict[str, str]
    recipient: str = Field(default="", max_length=300)


@dataclass(frozen=True)
class LetterPdf:
    pdf: bytes
    pages: int
    filename: str


def set_company_notes(conn: Conn, user_id: int, application_id: int, notes: str) -> bool:
    return bool(
        conn.execute(
            "UPDATE applications SET company_notes = %s, updated_at = now()"
            " WHERE user_id = %s AND id = %s AND deleted_at IS NULL",
            (notes.strip(), user_id, application_id),
        ).rowcount
    )


def _application(conn: Conn, user_id: int, application_id: int) -> dict[str, Any] | None:
    return conn.execute(
        "SELECT id, offer_id, title, company_name, company_notes FROM applications"
        " WHERE user_id = %s AND id = %s AND deleted_at IS NULL",
        (user_id, application_id),
    ).fetchone()


def _achievements(conn: Conn, user_id: int, application_id: int) -> list[AchievementInput]:
    """What the letter may draw on: the CV adapted for this application as the user
    settled it, or else the whole CV."""
    if drafts := list_drafts(conn, user_id, application_id):
        draft = load_draft(conn, user_id, drafts[0].id)
        if draft is not None:
            kept = [b for e in draft.experiences for b in [e, *e.bullets] if b.kept]
            kept += [item for item in [*draft.formation, *draft.competences] if item.kept]
            return [AchievementInput(id=item.id, text=item.text) for item in kept]
    stored = load_cv(conn, user_id, "fr")
    profile = parse_cv_markdown(stored.content if stored else "")
    return [
        AchievementInput(id=item.id, text=item.text)
        for item in profile.items
        if item.kind in ("experience", "bullet", "formation", "skill")
    ]


def propose_letter(
    conn: Conn, client: LLMClient, budget: Budget, user_id: int, application_id: int
) -> LetterView | None:
    """One call for every slot, then the checks. None: no such application. Raises
    `LetterNotPossibleError` before any call, and what `run_task` raises."""
    application = _application(conn, user_id, application_id)
    if application is None:
        return None
    stored = load_cv(conn, user_id, "fr")
    if stored is not None and find_personal_data(stored.content):
        raise LetterNotPossibleError(
            "Votre CV contient des coordonnées. Retirez-les dans « Mon CV » : elles vont "
            "dans l'identité, que le modèle ne lit jamais."
        )
    achievements = _achievements(conn, user_id, application_id)
    if not achievements:
        raise LetterNotPossibleError("Votre CV est vide : remplissez-le avant la lettre.")

    offer = get_offer(conn, user_id, application["offer_id"]) if application["offer_id"] else None
    title = offer.title if offer else application["title"]
    company = offer.company_name if offer else application["company_name"]
    description = offer.description_md if offer else ""
    notes = application["company_notes"]
    manifest = load_letter_manifest()
    style = StyleGuide()

    proposal, call_id = run_task(
        conn,
        client,
        budget,
        user_id,
        DRAFT_LETTER_TASK,
        DraftLetterInput(
            lang="fr",
            offer_title=title,
            offer_company=company,
            offer_description=description,
            company_notes=notes,
            template_name=manifest.name,
            slots=[
                LetterSlotInput(name=s.name, max_words=s.max_words, sources=s.sources)
                for s in manifest.slots
            ],
            achievements=achievements,
        ),
        redaction_values=redaction_values(conn, user_id),
    )
    # The checks read the texts as the user sees them, not the redacted copies sent.
    sources = LetterSources(
        realisations="\n".join(item.text for item in achievements),
        offre=f"{title}\n{company}\n{description}",
        notes_entreprise=notes,
    )
    draft = build_letter_draft(
        proposal, manifest, sources, style, known_ids={item.id for item in achievements}
    )
    row = conn.execute(
        """
        INSERT INTO letters (user_id, application_id, template, recipient, proposal, texts,
            llm_call_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        """,
        (
            user_id,
            application_id,
            manifest.name,
            company,
            Jsonb(draft.model_dump(mode="json")),
            Jsonb({slot.name: slot.text for slot in draft.slots}),
            call_id,
        ),
    ).fetchone()
    assert row is not None
    event(
        log,
        "letter.proposed",
        user_id=user_id,
        llm_call_id=call_id,
        letter_id=row["id"],
        application_id=application_id,
        refused=[slot.name for slot in draft.slots if slot.rejected_reason],
        unsourced=sum(len(slot.unsourced_names) for slot in draft.slots),
        warnings=len(draft.warnings),
    )
    return get_letter(conn, user_id, row["id"])


_COLUMNS = """
    l.id, l.application_id, l.recipient, l.proposal, l.texts, l.llm_call_id, l.created_at,
    l.updated_at, a.title AS application_title, a.company_name
"""


def list_letters(conn: Conn, user_id: int, application_id: int) -> list[LetterSummary]:
    rows = conn.execute(
        "SELECT id, application_id, llm_call_id, created_at, updated_at FROM letters"
        " WHERE user_id = %s AND application_id = %s ORDER BY created_at DESC, id DESC",
        (user_id, application_id),
    )
    return [LetterSummary.model_validate(row) for row in rows]


def delete_letter(conn: Conn, user_id: int, letter_id: int) -> bool:
    """Erased: a send that attached it froze its PDF in `documents`, and the model call
    stays in the journal."""
    deleted = conn.execute(
        "DELETE FROM letters WHERE user_id = %s AND id = %s", (user_id, letter_id)
    ).rowcount
    if deleted:
        event(log, "letter.deleted", user_id=user_id, letter_id=letter_id)
    return bool(deleted)


def get_letter(conn: Conn, user_id: int, letter_id: int) -> LetterView | None:
    row = conn.execute(
        f"""
        SELECT {_COLUMNS} FROM letters l JOIN applications a ON a.id = l.application_id
        WHERE l.user_id = %s AND l.id = %s AND a.deleted_at IS NULL
        """,  # nosec B608
        (user_id, letter_id),
    ).fetchone()
    if row is None:
        return None
    draft = LetterDraft.model_validate(row["proposal"])
    texts: dict[str, str] = row["texts"]
    manifest = load_letter_manifest()
    slots: list[SlotView] = []
    for spec in manifest.slots:
        proposed = next((s for s in draft.slots if s.name == spec.name), None)
        text = texts.get(spec.name, "")
        slots.append(
            SlotView(
                name=spec.name,
                max_words=spec.max_words,
                text=text,
                words=count_words(text),
                proposed=proposed.proposed if proposed else "",
                rejected_reason=proposed.rejected_reason if proposed else "",
                unsourced_names=proposed.unsourced_names if proposed else [],
            )
        )
    return LetterView(
        id=row["id"],
        application_id=row["application_id"],
        llm_call_id=row["llm_call_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        application_title=row["application_title"],
        company_name=row["company_name"],
        recipient=row["recipient"],
        slots=slots,
        cited_ids=draft.cited_ids,
        warnings=draft.warnings,
        problems=letter_problems(texts, manifest),
        max_pages=manifest.max_pages,
    )


def save_texts(conn: Conn, user_id: int, letter_id: int, body: LetterTexts) -> LetterView | None:
    """The user's texts. Only the template's slots are kept."""
    names = {spec.name for spec in load_letter_manifest().slots}
    texts = {name: text.strip()[:4000] for name, text in body.texts.items() if name in names}
    updated = conn.execute(
        "UPDATE letters SET texts = %s, recipient = %s, updated_at = now()"
        " WHERE user_id = %s AND id = %s",
        (Jsonb(texts), body.recipient.strip(), user_id, letter_id),
    ).rowcount
    return get_letter(conn, user_id, letter_id) if updated else None


def _filename(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", fold(name)).strip("-")
    return f"lettre-{slug}.pdf" if slug else "lettre.pdf"


def render(conn: Conn, user_id: int, letter_id: int, day: date | None = None) -> LetterPdf | None:
    """None: no such letter. Raises `LetterRenderError`. Logs carry no message from the
    render, which could quote the letter."""
    letter = get_letter(conn, user_id, letter_id)
    if letter is None:
        return None
    application = _application(conn, user_id, letter.application_id)
    assert application is not None
    offer = get_offer(conn, user_id, application["offer_id"]) if application["offer_id"] else None
    identity = load_identity(conn, user_id)
    try:
        rendered = render_letter(
            {slot.name: slot.text for slot in letter.slots},
            identity,
            offer_title=offer.title if offer else letter.application_title,
            recipient=letter.recipient,
            day=day or date.today(),
        )
    except PdfEngineUnavailable as error:
        log.error("Letter render: the PDF engine is unavailable")
        raise LetterRenderError(str(error)) from None
    except Exception as error:
        log.error("Letter render failed: %s", type(error).__name__)
        raise LetterRenderError("Le PDF n'a pas pu être produit.") from None
    return LetterPdf(pdf=rendered.pdf, pages=rendered.pages, filename=_filename(identity.name))

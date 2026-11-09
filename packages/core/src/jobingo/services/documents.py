"""The archive of attached documents: a PDF is rendered once, when a send is proposed,
and kept with its SHA-256. What leaves is these bytes, whatever the CV or the letter
becomes afterwards."""

import hashlib
import logging

from jobingo.db import Conn
from jobingo.domain.actions import Attachment, DocumentKind
from jobingo.logs import event
from jobingo.services import cv_drafts, cv_page, letters
from jobingo.services.applications import get_application

log = logging.getLogger(__name__)


class DocumentError(Exception):
    """The document cannot be attached as it stands. The message is shown, in French."""


def _store(
    conn: Conn,
    user_id: int,
    application_id: int | None,
    kind: DocumentKind,
    filename: str,
    content: bytes,
) -> Attachment:
    sha256 = hashlib.sha256(content).hexdigest()
    row = conn.execute(
        "INSERT INTO documents (user_id, application_id, kind, filename, sha256, content)"
        " VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (user_id, application_id, kind, filename, sha256, content),
    ).fetchone()
    assert row is not None
    event(log, "document.archived", user_id=user_id, document_id=row["id"], kind=kind)
    return Attachment(document_id=row["id"], filename=filename, sha256=sha256)


def archive_letter(conn: Conn, user_id: int, application_id: int, letter_id: int) -> Attachment:
    """Raises `DocumentError` for a letter of another application, or one that could
    not be downloaded either."""
    letter = letters.get_letter(conn, user_id, letter_id)
    if letter is None or letter.application_id != application_id:
        raise DocumentError("Cette lettre n'est pas celle de la candidature.")
    if letter.problems:
        raise DocumentError(f"La lettre ne peut pas partir : {letter.problems[0]}")
    try:
        pdf = letters.render(conn, user_id, letter_id)
    except letters.LetterRenderError as error:
        raise DocumentError(str(error)) from None
    assert pdf is not None
    if pdf.pages > letter.max_pages:
        raise DocumentError("La lettre dépasse une page.")
    return _store(conn, user_id, application_id, "letter", pdf.filename, pdf.pdf)


def archive_cv(conn: Conn, user_id: int, application_id: int) -> Attachment:
    """The CV adapted to the application's offer, from its latest draft, or else the CV
    page as it stands. Raises `DocumentError` for a CV that is not one whole page."""
    application = get_application(conn, user_id, application_id)
    if application is None:
        raise DocumentError("Candidature introuvable.")
    drafts = (
        cv_drafts.list_drafts(conn, user_id, offer_id=application.offer_id)
        if application.offer_id
        else []
    )
    try:
        pdf = (
            cv_drafts.render_draft(conn, user_id, drafts[0].id)
            if drafts
            else cv_page.render_page(conn, user_id, "fr")
        )
    except cv_page.CvRenderError as error:
        raise DocumentError(str(error)) from None
    assert pdf is not None
    if pdf.rendered.pages > 1 or pdf.missing_items:
        raise DocumentError("Le CV ne tient pas sur une page : ajustez-le avant de l'envoyer.")
    return _store(conn, user_id, application_id, "cv", pdf.filename, pdf.rendered.pdf)


def load(conn: Conn, user_id: int, document_id: int) -> tuple[str, bytes] | None:
    """The file name and the archived bytes."""
    row = conn.execute(
        "SELECT filename, content FROM documents WHERE user_id = %s AND id = %s",
        (user_id, document_id),
    ).fetchone()
    return (row["filename"], bytes(row["content"])) if row else None

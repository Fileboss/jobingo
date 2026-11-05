"""The only code that writes the source CV.

These are the user's own words, and every model flow reads them as its source, so
they must never be rewritten by a flow that could carry model output.
`tests/test_architecture.py` asserts that only the API's CV routes, a human's save,
import this module, and that no other module writes `cv_versions`.
"""

import psycopg

from jobingo.db import Conn
from jobingo.domain.cv_diagnostics import CvDiagnostic, diagnose_cv, diagnose_fields
from jobingo.domain.cv_document import CvDocument, CvLang, FormDraft, TextDraft, draft_markdown
from jobingo.domain.cv_fields import canonical_stored
from jobingo.domain.profile import parse_cv_markdown
from jobingo.services.cv import StoredCv, document_of, load_cv


class CvConflictError(Exception):
    """The stored CV is no longer the one the editor loaded."""

    def __init__(self, current: CvDocument) -> None:
        super().__init__("the stored CV changed since it was loaded")
        self.current = current


class CvRejectedError(Exception):
    """A duplicate id: the one thing that blocks a save."""

    def __init__(self, diagnostics: list[CvDiagnostic]) -> None:
        super().__init__("the CV has a duplicate id")
        self.diagnostics = diagnostics


def _sha256_of(stored: StoredCv | None) -> str | None:
    return stored.sha256 if stored else None


def save_cv(
    conn: Conn,
    user_id: int,
    lang: CvLang,
    draft: TextDraft | FormDraft,
    expected_sha256: str | None,
) -> CvDocument:
    """Store the draft as a new version, in canonical form with its ids attached.

    `expected_sha256` is the hash of the stored content the editor loaded: a save
    never overwrites a change made elsewhere. A save without a real change adds no
    version. Raises `CvConflictError` and `CvRejectedError`.
    """
    previous = load_cv(conn, user_id, lang)
    if _sha256_of(previous) != expected_sha256:
        raise CvConflictError(document_of(previous, lang))

    typed = draft_markdown(draft, lang)
    stored = canonical_stored(typed, previous.content if previous else "", lang)
    if not parse_cv_markdown(stored).is_valid:
        raise CvRejectedError([d for d in diagnose_cv(typed) if d.code == "duplicate_id"])

    saved = previous
    if previous is None or stored != previous.content:
        version = previous.version + 1 if previous else 1
        try:
            conn.execute(
                "INSERT INTO cv_versions (user_id, lang, version, content) VALUES (%s, %s, %s, %s)",
                (user_id, lang, version, stored),
            )
        except psycopg.errors.UniqueViolation as error:
            # Another save took this version between the read and this write.
            raise CvConflictError(document_of(load_cv(conn, user_id, lang), lang)) from error
        saved = load_cv(conn, user_id, lang)

    document = document_of(saved, lang)
    if isinstance(draft, FormDraft):
        # A dropped keyword is no longer in what was stored: say so now.
        dropped = diagnose_fields(draft.fields)
        return document.model_copy(update={"diagnostics": dropped + document.diagnostics})
    return document

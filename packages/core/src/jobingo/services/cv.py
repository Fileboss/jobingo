"""Reading the source CV. Writing it is `services.cv_editor`'s alone."""

import hashlib
from dataclasses import dataclass
from datetime import datetime

from jobingo.db import Conn
from jobingo.domain.cv_document import CvDocument, CvLang, view_of_stored
from jobingo.domain.cv_fields import CvFields


@dataclass(frozen=True)
class StoredCv:
    version: int
    content: str
    updated_at: datetime

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


def load_cv(conn: Conn, user_id: int, lang: CvLang) -> StoredCv | None:
    row = conn.execute(
        """
        SELECT version, content, created_at
        FROM cv_versions
        WHERE user_id = %s AND lang = %s
        ORDER BY version DESC
        LIMIT 1
        """,
        (user_id, lang),
    ).fetchone()
    if row is None:
        return None
    return StoredCv(version=row["version"], content=row["content"], updated_at=row["created_at"])


def document_of(stored: StoredCv | None, lang: CvLang) -> CvDocument:
    if stored is None:
        return CvDocument(
            lang=lang,
            text="",
            fields=CvFields(),
            diagnostics=[],
            sha256=None,
            version=0,
            updated_at=None,
        )
    return CvDocument(
        **dict(view_of_stored(stored.content, lang)),
        sha256=stored.sha256,
        version=stored.version,
        updated_at=stored.updated_at,
    )

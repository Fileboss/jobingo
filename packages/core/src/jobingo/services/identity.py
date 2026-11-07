"""The identity and the photo, in their own table, apart from the CV."""

from jobingo.db import Conn
from jobingo.domain.identity import Identity
from jobingo.services.photo import decode_upload


def load_identity(conn: Conn, user_id: int) -> Identity:
    row = conn.execute(
        """
        SELECT name, email, phone, address, linkedin, github
        FROM identities
        WHERE user_id = %s
        """,
        (user_id,),
    ).fetchone()
    return Identity.model_validate(row) if row else Identity()


def redaction_values(conn: Conn, user_id: int) -> list[str]:
    """The values to replace with `[CANDIDAT]` in everything sent to the model.

    `llm` cannot import identity, so redaction is decided here, above it, and handed
    down as opaque strings that `llm.journal.run_task` requires.
    """
    identity = load_identity(conn, user_id)
    return [value for value in (identity.name, identity.email, identity.phone) if value]


def save_identity(conn: Conn, user_id: int, identity: Identity) -> None:
    conn.execute(
        """
        INSERT INTO identities (user_id, name, email, phone, address, linkedin, github)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            name = EXCLUDED.name,
            email = EXCLUDED.email,
            phone = EXCLUDED.phone,
            address = EXCLUDED.address,
            linkedin = EXCLUDED.linkedin,
            github = EXCLUDED.github,
            updated_at = now()
        """,
        (
            user_id,
            identity.name,
            identity.email,
            identity.phone,
            identity.address,
            identity.linkedin,
            identity.github,
        ),
    )


def has_photo(conn: Conn, user_id: int) -> bool:
    row = conn.execute(
        "SELECT photo IS NOT NULL AS present FROM identities WHERE user_id = %s", (user_id,)
    ).fetchone()
    return row is not None and row["present"]


def load_photo(conn: Conn, user_id: int) -> bytes | None:
    row = conn.execute("SELECT photo FROM identities WHERE user_id = %s", (user_id,)).fetchone()
    return row["photo"] if row else None


def save_photo(conn: Conn, user_id: int, data_base64: str) -> None:
    """Raises `InvalidPhotoError`, with the message for the user."""
    photo = decode_upload(data_base64)
    conn.execute(
        """
        INSERT INTO identities (user_id, photo) VALUES (%s, %s)
        ON CONFLICT (user_id) DO UPDATE SET photo = EXCLUDED.photo, updated_at = now()
        """,
        (user_id, photo),
    )


def remove_photo(conn: Conn, user_id: int) -> None:
    conn.execute(
        "UPDATE identities SET photo = NULL, updated_at = now() WHERE user_id = %s", (user_id,)
    )

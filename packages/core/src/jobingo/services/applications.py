"""Applications: created from an offer or by hand, followed through their events."""

import logging
from typing import Any

from psycopg import errors

from jobingo.db import Conn
from jobingo.domain.applications import (
    ApplicationEvent,
    ApplicationSummary,
    ApplicationView,
    Contact,
    NewApplication,
    NewEvent,
    derive_status,
    next_follow_up,
    tone,
)
from jobingo.logs import event
from jobingo.services.offers import get_offer

log = logging.getLogger(__name__)

_COLUMNS = """
    id, offer_id, title, company_name, contact_name, contact_email, contact_phone,
    company_notes, created_at
"""


def _events(conn: Conn, user_id: int, application_id: int) -> list[ApplicationEvent]:
    rows = conn.execute(
        """
        SELECT id, type, occurred_at, note, created_at FROM application_events
        WHERE user_id = %s AND application_id = %s ORDER BY occurred_at DESC, id DESC
        """,
        (user_id, application_id),
    )
    return [ApplicationEvent.model_validate(row) for row in rows]


def _summary(row: dict[str, Any], events: list[ApplicationEvent]) -> dict[str, Any]:
    status = derive_status(events)
    return {
        "id": row["id"],
        "offer_id": row["offer_id"],
        "title": row["title"],
        "company_name": row["company_name"],
        "status": status,
        "tone": tone(status, events),
        "last_event": events[0] if events else None,
        "follow_up_on": next_follow_up(events),
        "created_at": row["created_at"],
    }


def list_applications(conn: Conn, user_id: int) -> list[ApplicationSummary]:
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM applications WHERE user_id = %s AND deleted_at IS NULL"
        " ORDER BY created_at DESC, id DESC",
        (user_id,),
    ).fetchall()
    return [
        ApplicationSummary.model_validate(_summary(row, _events(conn, user_id, row["id"])))
        for row in rows
    ]


def get_application(conn: Conn, user_id: int, application_id: int) -> ApplicationView | None:
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM applications"
        " WHERE user_id = %s AND id = %s AND deleted_at IS NULL",
        (user_id, application_id),
    ).fetchone()
    if row is None:
        return None
    events = _events(conn, user_id, application_id)
    contact = Contact(
        name=row["contact_name"], email=row["contact_email"], phone=row["contact_phone"]
    )
    return ApplicationView.model_validate(
        _summary(row, events)
        | {"contact": contact, "events": events, "company_notes": row["company_notes"]}
    )


def application_for_offer(conn: Conn, user_id: int, offer_id: int) -> int | None:
    row = conn.execute(
        "SELECT id FROM applications WHERE user_id = %s AND offer_id = %s AND deleted_at IS NULL",
        (user_id, offer_id),
    ).fetchone()
    return row["id"] if row else None


def create_application(conn: Conn, user_id: int, new: NewApplication) -> ApplicationView:
    row = conn.execute(
        "INSERT INTO applications (user_id, title, company_name) VALUES (%s, %s, %s) RETURNING id",
        (user_id, new.title.strip(), new.company_name.strip()),
    ).fetchone()
    assert row is not None
    event(log, "application.created", user_id=user_id, application_id=row["id"])
    view = get_application(conn, user_id, row["id"])
    assert view is not None
    return view


def apply_to_offer(conn: Conn, user_id: int, offer_id: int) -> ApplicationView | None:
    """The offer's application, created if there is none yet. Applying is keeping the
    offer, so it is marked as kept unless the user already decided. None: no offer."""
    offer = get_offer(conn, user_id, offer_id)
    if offer is None:
        return None
    existing = application_for_offer(conn, user_id, offer_id)
    if existing is None:
        try:
            with conn.transaction():
                row = conn.execute(
                    "INSERT INTO applications (user_id, offer_id, title, company_name)"
                    " VALUES (%s, %s, %s, %s) RETURNING id",
                    (user_id, offer_id, offer.title, offer.company_name),
                ).fetchone()
                assert row is not None
                existing = row["id"]
                conn.execute(
                    "UPDATE offers SET decision = 'shortlisted' WHERE user_id = %s AND id = %s"
                    " AND decision IS NULL",
                    (user_id, offer_id),
                )
        except errors.UniqueViolation:
            # A second click raced the first: there is one application, the other's.
            existing = application_for_offer(conn, user_id, offer_id)
        event(
            log, "application.created", user_id=user_id, application_id=existing, offer_id=offer_id
        )
    assert existing is not None
    return get_application(conn, user_id, existing)


def _refresh_status(conn: Conn, user_id: int, application_id: int) -> None:
    status = derive_status(_events(conn, user_id, application_id))
    conn.execute(
        "UPDATE applications SET status = %s, updated_at = now() WHERE user_id = %s AND id = %s",
        (status, user_id, application_id),
    )


def add_event(
    conn: Conn, user_id: int, application_id: int, new: NewEvent
) -> ApplicationView | None:
    if get_application(conn, user_id, application_id) is None:
        return None
    with conn.transaction():
        conn.execute(
            "INSERT INTO application_events (user_id, application_id, type, occurred_at, note)"
            " VALUES (%s, %s, %s, %s, %s)",
            (user_id, application_id, new.type, new.occurred_at, new.note.strip()),
        )
        _refresh_status(conn, user_id, application_id)
    event(
        log,
        "application.event_added",
        user_id=user_id,
        application_id=application_id,
        type=new.type,
    )
    return get_application(conn, user_id, application_id)


def remove_event(
    conn: Conn, user_id: int, application_id: int, event_id: int
) -> ApplicationView | None:
    with conn.transaction():
        deleted = conn.execute(
            "DELETE FROM application_events WHERE user_id = %s AND application_id = %s AND id = %s",
            (user_id, application_id, event_id),
        ).rowcount
        if not deleted:
            return None
        _refresh_status(conn, user_id, application_id)
    return get_application(conn, user_id, application_id)


def set_contact(
    conn: Conn, user_id: int, application_id: int, contact: Contact
) -> ApplicationView | None:
    updated = conn.execute(
        """
        UPDATE applications SET contact_name = %s, contact_email = %s, contact_phone = %s,
            updated_at = now()
        WHERE user_id = %s AND id = %s AND deleted_at IS NULL
        """,
        (contact.name.strip(), contact.email, contact.phone.strip(), user_id, application_id),
    ).rowcount
    return get_application(conn, user_id, application_id) if updated else None


def delete_application(conn: Conn, user_id: int, application_id: int) -> bool:
    """Hidden, not erased: its events stay, for the record. The offer is free again."""
    deleted = conn.execute(
        "UPDATE applications SET deleted_at = now() WHERE user_id = %s AND id = %s"
        " AND deleted_at IS NULL",
        (user_id, application_id),
    ).rowcount
    if deleted:
        event(log, "application.deleted", user_id=user_id, application_id=application_id)
    return bool(deleted)

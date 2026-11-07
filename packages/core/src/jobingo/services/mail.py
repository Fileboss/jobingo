"""The mailbox: read it, store what is new, read job alerts for their offers.

A sync stores first and decides after: storing never needs the model, so a message is
kept even when the model is not configured or a call fails, and the next sync resumes
from what is stored, without reading the mailbox again."""

import logging
from datetime import date, timedelta
from typing import Any

from jobingo.config import Settings
from jobingo.connectors.imap import ImapMailbox
from jobingo.connectors.mail import MailSource
from jobingo.db import Conn
from jobingo.domain.linkedin_alert import is_linkedin_sender, parse_linkedin_alert
from jobingo.domain.mail import (
    FolderState,
    MailboxStatus,
    Message,
    MessageKind,
    MessageSummary,
    RawMessage,
    SyncReport,
    excerpt,
)
from jobingo.llm.client import LLMCallError, LLMClient
from jobingo.llm.journal import Budget, LLMBudgetExceeded
from jobingo.logs import event
from jobingo.services import offers as offers_service
from jobingo.services.scoring import score_many

log = logging.getLogger(__name__)

# The first sync of a folder reads this far back, not the whole mailbox.
FIRST_SYNC_DAYS = 30
# Messages read per folder and per sync; the next sync reads the rest.
MAX_PER_SYNC = 200
# What of an alert reaches the model: a digest's offers sit near the top.
_MAX_ALERT_CHARS = 20_000


def mailbox_from_settings(settings: Settings) -> ImapMailbox:
    """Raises `MailboxError` for a setting that cannot be used."""
    return ImapMailbox(
        settings.mail_imap_host,
        settings.mail_imap_port,
        settings.mail_imap_ssl,
        settings.mail_imap_user,
        settings.mail_imap_password.get_secret_value(),
    )


def folders(settings: Settings) -> list[str]:
    """The inbox, then the alert folder when a filter moves alerts out of it."""
    return list(dict.fromkeys((settings.mail_inbox_folder, settings.mail_alert_folder)))


def is_local(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")


# --- reading -------------------------------------------------------------------


def _store(conn: Conn, user_id: int, mailbox: str, folder: str, raw: RawMessage) -> bool:
    """False when the message is already stored."""
    row = conn.execute(
        """
        INSERT INTO messages (user_id, mailbox, folder, message_id, thread_id, in_reply_to,
            from_addr, to_addrs, subject, body_text, body_html, list_unsubscribe, received_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, mailbox, message_id) DO NOTHING
        RETURNING id
        """,
        (
            user_id,
            mailbox,
            folder,
            raw.message_id,
            raw.thread_id,
            raw.in_reply_to,
            raw.from_addr,
            raw.to_addrs,
            raw.subject,
            raw.body_text,
            raw.body_html,
            raw.list_unsubscribe,
            raw.received_at,
        ),
    ).fetchone()
    return row is not None


def ingest_folder(
    conn: Conn, user_id: int, source: MailSource, folder: str, today: date | None = None
) -> SyncReport:
    """Store what is new in `folder` and move its cursor. Raises `MailboxError`."""
    mailbox = source.address
    state = conn.execute(
        "SELECT uidvalidity, last_uid FROM mail_folders"
        " WHERE user_id = %s AND mailbox = %s AND folder = %s",
        (user_id, mailbox, folder),
    ).fetchone()
    since = (today or date.today()) - timedelta(days=FIRST_SYNC_DAYS)
    after = state["last_uid"] if state else 0
    result = source.fetch(folder, after, since, MAX_PER_SYNC)
    renumbered = state is not None and state["uidvalidity"] != result.uidvalidity
    if renumbered:
        after = 0
        result = source.fetch(folder, 0, since, MAX_PER_SYNC)

    report = SyncReport(has_more=result.has_more)
    with conn.transaction():
        for raw in result.messages:
            if _store(conn, user_id, mailbox, folder, raw):
                report.fetched += 1
            else:
                report.duplicates += 1
            after = max(after, raw.uid)
        conn.execute(
            """
            INSERT INTO mail_folders (user_id, mailbox, folder, uidvalidity, last_uid, synced_at)
            VALUES (%s, %s, %s, %s, %s, now())
            ON CONFLICT (user_id, mailbox, folder) DO UPDATE SET
                uidvalidity = excluded.uidvalidity, last_uid = excluded.last_uid,
                synced_at = excluded.synced_at
            """,
            (user_id, mailbox, folder, result.uidvalidity, after),
        )
    event(
        log,
        "mail.fetched",
        user_id=user_id,
        folder=folder,
        new=report.fetched,
        duplicates=report.duplicates,
        renumbered=renumbered,
        has_more=result.has_more,
    )
    return report


# --- sorting and alerts --------------------------------------------------------


def _set_kind(conn: Conn, user_id: int, message_id: int, kind: MessageKind, done: bool) -> None:
    conn.execute(
        "UPDATE messages SET kind = %s, processed_at = CASE WHEN %s THEN now() END"
        " WHERE user_id = %s AND id = %s",
        (kind, done, user_id, message_id),
    )


def _sort_new(conn: Conn, user_id: int, settings: Settings) -> list[int]:
    """Give each new message its kind. A LinkedIn alert is read here, in code; an
    alert from another sender waits for the model. Returns the offers stored."""
    dedicated = settings.mail_alert_folder != settings.mail_inbox_folder
    rows = conn.execute(
        "SELECT id, folder, from_addr, body_html FROM messages"
        " WHERE user_id = %s AND kind IS NULL ORDER BY received_at, id",
        (user_id,),
    ).fetchall()
    offer_ids: list[int] = []
    for row in rows:
        cards = (
            parse_linkedin_alert(row["body_html"]) if is_linkedin_sender(row["from_addr"]) else []
        )
        if cards:
            stored = offers_service.store_alert_offers(conn, user_id, cards, row["id"])
            _set_kind(conn, user_id, row["id"], "alert", done=True)
            offer_ids += [offer.id for offer in stored if offer.id not in offer_ids]
            event(
                log,
                "mail.alert_read",
                user_id=user_id,
                message_id=row["id"],
                parser="linkedin",
                offers=len(stored),
            )
        elif dedicated and row["folder"] == settings.mail_alert_folder:
            _set_kind(conn, user_id, row["id"], "alert", done=False)
        else:
            # Classified at the next step of the build; until then, shown as received.
            _set_kind(conn, user_id, row["id"], "message", done=False)
    return offer_ids


def _extract_waiting_alerts(
    conn: Conn, client: LLMClient, budget: Budget, user_id: int, report: SyncReport
) -> list[int]:
    """Alerts from other senders, through `extract_offer`. Stops at a spending cap or a
    failed call: the alert stays waiting, for the next sync."""
    rows = conn.execute(
        "SELECT id, subject, body_text FROM messages WHERE user_id = %s AND kind = 'alert'"
        " AND processed_at IS NULL ORDER BY received_at, id",
        (user_id,),
    ).fetchall()
    offer_ids: list[int] = []
    for index, row in enumerate(rows):
        text = f"{row['subject']}\n\n{row['body_text']}"[:_MAX_ALERT_CHARS]
        try:
            result = offers_service.intake(conn, client, budget, user_id, text, row["id"])
            stored = [offer.id for offer in result.offers]
        except offers_service.NoOfferFoundError:
            stored = []
        except (LLMCallError, LLMBudgetExceeded) as error:
            report.waiting = len(rows) - index
            report.error = (
                str(error)
                if isinstance(error, LLMBudgetExceeded)
                else "le modèle n'a pas pu lire une alerte"
            )
            event(
                log,
                "mail.alert_failed",
                logging.WARNING,
                user_id=user_id,
                message_id=row["id"],
                waiting=report.waiting,
                error=type(error).__name__,
            )
            break
        conn.execute(
            "UPDATE messages SET processed_at = now() WHERE user_id = %s AND id = %s",
            (user_id, row["id"]),
        )
        offer_ids += [offer_id for offer_id in stored if offer_id not in offer_ids]
        event(
            log,
            "mail.alert_read",
            user_id=user_id,
            message_id=row["id"],
            parser="extract_offer",
            offers=len(stored),
        )
    return offer_ids


def waiting_count(conn: Conn, user_id: int) -> int:
    row = conn.execute(
        "SELECT count(*) AS n FROM messages WHERE user_id = %s AND kind = 'alert'"
        " AND processed_at IS NULL",
        (user_id,),
    ).fetchone()
    return row["n"] if row else 0


def sync(
    conn: Conn,
    settings: Settings,
    source: MailSource,
    client: LLMClient | None,
    budget: Budget,
    user_id: int,
) -> SyncReport:
    """Read every folder, read the alerts, score the new offers. Without a model, the
    LinkedIn alerts are still read and their offers stored, unscored.

    Raises `MailboxError` when the mailbox cannot be read: nothing is decided then."""
    report = SyncReport()
    for folder in folders(settings):
        read = ingest_folder(conn, user_id, source, folder)
        report.fetched += read.fetched
        report.duplicates += read.duplicates
        report.has_more = report.has_more or read.has_more

    alerts_before = _alert_count(conn, user_id)
    offer_ids = _sort_new(conn, user_id, settings)
    if client is not None:
        offer_ids += [
            offer_id
            for offer_id in _extract_waiting_alerts(conn, client, budget, user_id, report)
            if offer_id not in offer_ids
        ]
    else:
        report.waiting = waiting_count(conn, user_id)
    report.alerts = _alert_count(conn, user_id) - alerts_before
    report.offer_ids = offer_ids

    if offer_ids and client is not None and report.error is None:
        run = score_many(conn, client, budget, user_id, offer_ids)
        report.unscored_ids = run.unscored_ids
        report.error = run.error
    else:
        report.unscored_ids = list(offer_ids)
    event(
        log,
        "mail.synced",
        logging.WARNING if report.error else logging.INFO,
        user_id=user_id,
        fetched=report.fetched,
        alerts=report.alerts,
        offers=len(offer_ids),
        unscored=len(report.unscored_ids),
        waiting=report.waiting,
        model=client is not None,
    )
    return report


def _alert_count(conn: Conn, user_id: int) -> int:
    row = conn.execute(
        "SELECT count(*) AS n FROM messages WHERE user_id = %s AND kind = 'alert'", (user_id,)
    ).fetchone()
    return row["n"] if row else 0


# --- display -------------------------------------------------------------------

_SUMMARY = """
    m.id, m.folder, m.from_addr, m.subject, m.received_at, m.kind, m.body_text,
    (SELECT count(*) FROM offers o WHERE o.user_id = m.user_id AND o.message_id = m.id)
        AS offer_count
"""


def _summary(row: dict[str, Any]) -> MessageSummary:
    return MessageSummary.model_validate({**row, "excerpt": excerpt(row["body_text"])})


def list_messages(
    conn: Conn, user_id: int, kind: MessageKind | None = None
) -> list[MessageSummary]:
    """Newest first."""
    rows = conn.execute(
        f"SELECT {_SUMMARY} FROM messages m WHERE m.user_id = %s"
        " AND (%s::text IS NULL OR m.kind = %s) ORDER BY m.received_at DESC, m.id DESC",
        (user_id, kind, kind),
    ).fetchall()
    return [_summary(row) for row in rows]


def get_message(conn: Conn, user_id: int, message_id: int) -> Message | None:
    row = conn.execute(
        f"SELECT {_SUMMARY}, m.to_addrs, m.processed_at FROM messages m"
        " WHERE m.user_id = %s AND m.id = %s",
        (user_id, message_id),
    ).fetchone()
    if row is None:
        return None
    offer_ids = [
        offer["id"]
        for offer in conn.execute(
            "SELECT id FROM offers WHERE user_id = %s AND message_id = %s ORDER BY id",
            (user_id, message_id),
        )
    ]
    return Message.model_validate(
        {**row, "excerpt": excerpt(row["body_text"]), "offer_ids": offer_ids}
    )


def status(conn: Conn, settings: Settings, user_id: int) -> MailboxStatus:
    address = settings.mail_imap_user
    synced = {
        row["folder"]: row["synced_at"]
        for row in conn.execute(
            "SELECT folder, synced_at FROM mail_folders WHERE user_id = %s AND mailbox = %s",
            (user_id, address),
        )
    }
    return MailboxStatus(
        address=address,
        host=settings.mail_imap_host,
        local=is_local(settings.mail_imap_host),
        dry_run=settings.smtp_dry_run,
        folders=[
            FolderState(folder=name, synced_at=synced.get(name)) for name in folders(settings)
        ],
        waiting=waiting_count(conn, user_id),
    )

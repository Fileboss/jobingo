"""The mailbox: read it, store what is new, read job alerts for their offers, classify
the other messages and tie them to the applications they concern.

A sync stores first and decides after: storing never needs the model, so a message is
kept even when the model is not configured or a call fails, and the next sync resumes
from what is stored, without reading the mailbox again.

The model only classifies. What follows is code: rules hide newsletters and blocked
senders before any call, matching ties a message to an application, and a status change
the message suggests becomes an event on the user's click only."""

import logging
from datetime import date, timedelta
from typing import Any, Literal

from jobingo.config import Settings
from jobingo.connectors.imap import ImapMailbox
from jobingo.connectors.mail import MailSource
from jobingo.db import Conn
from jobingo.domain.linkedin_alert import is_linkedin_sender, parse_linkedin_alert
from jobingo.domain.mail import (
    COMPANY_SIMILARITY_THRESHOLD,
    MATCHED_CATEGORIES,
    SUGGESTED_EVENT,
    Category,
    FolderState,
    HiddenReason,
    LinkedBy,
    MailboxStatus,
    Message,
    MessageKind,
    MessageSummary,
    RawMessage,
    Suggestion,
    SyncReport,
    bare_address,
    company_similarity,
    excerpt,
    parse_iso_date,
)
from jobingo.llm.client import LLMCallError, LLMClient
from jobingo.llm.journal import Budget, LLMBudgetExceeded, run_task
from jobingo.llm.tasks.classify_message import CLASSIFY_MESSAGE_TASK, ClassifyMessageInput
from jobingo.logs import event
from jobingo.services import applications as applications_service
from jobingo.services import offers as offers_service
from jobingo.services.identity import redaction_values
from jobingo.services.scoring import score_many

log = logging.getLogger(__name__)

# The first sync of a folder reads this far back, not the whole mailbox.
FIRST_SYNC_DAYS = 30
# Messages read per folder and per sync; the next sync reads the rest.
MAX_PER_SYNC = 200
# What of an alert reaches the model: a digest's offers sit near the top.
_MAX_ALERT_CHARS = 20_000
# What of a message reaches the model: a long thread quoted below the new text adds
# cost, not signal.
_MAX_MESSAGE_CHARS = 8_000


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


def _blocked(conn: Conn, user_id: int) -> set[str]:
    return {
        row["address"]
        for row in conn.execute(
            "SELECT address FROM blocked_senders WHERE user_id = %s", (user_id,)
        )
    }


def _rule(row: dict[str, Any], blocked: set[str]) -> HiddenReason | None:
    """Hidden without the model: less mail reaches it, and none of these is news of an
    application. A message the user restores goes to the model at the next sync."""
    if bare_address(row["from_addr"]) in blocked:
        return "blocked_sender"
    if row["list_unsubscribe"]:
        return "newsletter"
    return None


def _sort_new(conn: Conn, user_id: int, settings: Settings, report: SyncReport) -> list[int]:
    """Give each new message its kind. A LinkedIn alert is read here, in code; an
    alert from another sender waits for the model, and so does a message, unless a rule
    hides it. Returns the offers stored."""
    dedicated = settings.mail_alert_folder != settings.mail_inbox_folder
    blocked = _blocked(conn, user_id)
    rows = conn.execute(
        "SELECT id, folder, from_addr, body_html, list_unsubscribe FROM messages"
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
        elif reason := _rule(row, blocked):
            _set_kind(conn, user_id, row["id"], "message", done=True)
            _set_hidden(conn, user_id, row["id"], reason)
            report.hidden += 1
            event(log, "message.hidden", user_id=user_id, message_id=row["id"], reason=reason)
        else:
            _set_kind(conn, user_id, row["id"], "message", done=False)
    return offer_ids


def _set_hidden(conn: Conn, user_id: int, message_id: int, reason: HiddenReason | None) -> None:
    conn.execute(
        "UPDATE messages SET hidden_reason = %s WHERE user_id = %s AND id = %s",
        (reason, user_id, message_id),
    )


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
            report.error = _stopped(error, "le modèle n'a pas pu lire une alerte")
            event(
                log,
                "mail.alert_failed",
                logging.WARNING,
                user_id=user_id,
                message_id=row["id"],
                left=len(rows) - index,
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


def _stopped(error: LLMCallError | LLMBudgetExceeded, failed: str) -> str:
    return str(error) if isinstance(error, LLMBudgetExceeded) else failed


# --- classifying and matching ----------------------------------------------------


def _classify(
    conn: Conn, client: LLMClient, budget: Budget, user_id: int, row: dict[str, Any]
) -> Category:
    """Stored at once, before anything else is tried: a later step that fails is
    retried at the next sync without paying for the classification again."""
    output, call_id = run_task(
        conn,
        client,
        budget,
        user_id,
        CLASSIFY_MESSAGE_TASK,
        ClassifyMessageInput(
            from_addr=row["from_addr"],
            subject=row["subject"],
            body_text=row["body_text"][:_MAX_MESSAGE_CHARS],
        ),
        redaction_values=redaction_values(conn, user_id),
    )
    category = output.category
    suggestion = SUGGESTED_EVENT.get(category)
    on = parse_iso_date(output.interview_date) if category == "interview" else None
    conn.execute(
        """
        UPDATE messages SET category = %s, company_hint = %s, summary = %s, llm_call_id = %s,
            hidden_reason = %s, suggestion_type = %s, suggestion_date = %s,
            suggestion_status = %s
        WHERE user_id = %s AND id = %s
        """,
        (
            category,
            output.company_name.strip()[:300],
            output.summary.strip()[:500],
            call_id,
            "other" if category == "other" else None,
            suggestion,
            on,
            "pending" if suggestion else None,
            user_id,
            row["id"],
        ),
    )
    event(
        log,
        "message.classified",
        user_id=user_id,
        message_id=row["id"],
        llm_call_id=call_id,
        category=category,
        suggestion=suggestion,
        dated=on is not None,
    )
    return category


type MatchedBy = Literal["thread", "contact", "company"]


def match_application(conn: Conn, user_id: int, message_id: int) -> tuple[int, MatchedBy] | None:
    """In this order: the thread of a message already tied to an application, the
    application's contact address, then a company name close to the one the model read.
    Anything else is left to the user."""
    message = conn.execute(
        "SELECT thread_id, from_addr, company_hint FROM messages WHERE user_id = %s AND id = %s",
        (user_id, message_id),
    ).fetchone()
    if message is None:
        return None
    thread = conn.execute(
        """
        SELECT a.id FROM messages m JOIN applications a ON a.id = m.application_id
        WHERE m.user_id = %s AND m.thread_id = %s AND m.id <> %s AND a.deleted_at IS NULL
        ORDER BY m.received_at DESC, m.id DESC LIMIT 1
        """,
        (user_id, message["thread_id"], message_id),
    ).fetchone()
    if thread:
        return thread["id"], "thread"
    sender = bare_address(message["from_addr"])
    contact = conn.execute(
        "SELECT id FROM applications WHERE user_id = %s AND deleted_at IS NULL"
        " AND contact_email <> '' AND lower(contact_email) = %s"
        " ORDER BY created_at DESC, id DESC LIMIT 1",
        (user_id, sender),
    ).fetchone()
    if contact:
        return contact["id"], "contact"
    if not message["company_hint"]:
        return None
    best: tuple[float, int] | None = None
    for row in conn.execute(
        "SELECT id, company_name FROM applications WHERE user_id = %s AND deleted_at IS NULL"
        " ORDER BY created_at DESC, id DESC",
        (user_id,),
    ):
        similarity = company_similarity(message["company_hint"], row["company_name"])
        if similarity > COMPANY_SIMILARITY_THRESHOLD and (best is None or similarity > best[0]):
            best = (similarity, row["id"])
    return (best[1], "company") if best else None


def _classify_waiting(
    conn: Conn, client: LLMClient, budget: Budget, user_id: int, report: SyncReport
) -> list[int]:
    """Classify each message waiting, read the offers of one that describes a job, and
    tie the others to their application. Stops at a spending cap or a failed call: the
    message stays waiting, for the next sync. Returns the offers stored."""
    rows = conn.execute(
        "SELECT id, from_addr, subject, body_text, category, application_id FROM messages"
        " WHERE user_id = %s AND kind = 'message' AND processed_at IS NULL"
        " ORDER BY received_at, id",
        (user_id,),
    ).fetchall()
    offer_ids: list[int] = []
    for index, row in enumerate(rows):
        category: Category | None = row["category"]
        stored: list[int] = []
        try:
            if category is None:
                category = _classify(conn, client, budget, user_id, row)
                report.classified += 1
            if category == "offer":
                text = f"{row['subject']}\n\n{row['body_text']}"[:_MAX_MESSAGE_CHARS]
                try:
                    result = offers_service.intake(conn, client, budget, user_id, text, row["id"])
                    stored = [offer.id for offer in result.offers]
                except offers_service.NoOfferFoundError:
                    pass
        except (LLMCallError, LLMBudgetExceeded) as error:
            report.error = _stopped(error, "le modèle n'a pas pu classer un message")
            event(
                log,
                "mail.message_failed",
                logging.WARNING,
                user_id=user_id,
                message_id=row["id"],
                left=len(rows) - index,
                error=type(error).__name__,
            )
            break
        # A message the user tied by hand while it waited keeps their choice.
        matched = (
            match_application(conn, user_id, row["id"])
            if category in MATCHED_CATEGORIES and row["application_id"] is None
            else None
        )
        if matched:
            link_application(conn, user_id, row["id"], matched[0], by="match")
            report.linked += 1
        conn.execute(
            "UPDATE messages SET processed_at = now() WHERE user_id = %s AND id = %s",
            (user_id, row["id"]),
        )
        offer_ids += [offer_id for offer_id in stored if offer_id not in offer_ids]
        event(
            log,
            "message.processed",
            user_id=user_id,
            message_id=row["id"],
            category=category,
            offers=len(stored),
            application_id=matched[0] if matched else None,
            matched_by=matched[1] if matched else None,
        )
    return offer_ids


def waiting_count(conn: Conn, user_id: int) -> int:
    """Alerts and messages the model has not read yet."""
    row = conn.execute(
        "SELECT count(*) AS n FROM messages WHERE user_id = %s AND kind IS NOT NULL"
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
    """Read every folder, read the alerts, classify the messages, score the new offers.
    Without a model, the LinkedIn alerts are still read and their offers stored,
    unscored, and the rules still hide newsletters and blocked senders.

    Raises `MailboxError` when the mailbox cannot be read: nothing is decided then."""
    report = SyncReport()
    for folder in folders(settings):
        read = ingest_folder(conn, user_id, source, folder)
        report.fetched += read.fetched
        report.duplicates += read.duplicates
        report.has_more = report.has_more or read.has_more

    alerts_before = _alert_count(conn, user_id)
    offer_ids = _sort_new(conn, user_id, settings, report)
    if client is not None:
        read = _extract_waiting_alerts(conn, client, budget, user_id, report)
        if report.error is None:
            read += _classify_waiting(conn, client, budget, user_id, report)
        offer_ids += [offer_id for offer_id in read if offer_id not in offer_ids]
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
        classified=report.classified,
        hidden=report.hidden,
        linked=report.linked,
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

# A deleted application lets go of its messages here, not in the table: restoring it
# would find them again.
_SUMMARY = """
    m.id, m.folder, m.from_addr, m.subject, m.received_at, m.kind, m.body_text,
    m.category, m.summary, m.hidden_reason, a.id AS application_id,
    a.title AS application_title, m.suggestion_type, m.suggestion_date, m.suggestion_status,
    (SELECT count(*) FROM offers o WHERE o.user_id = m.user_id AND o.message_id = m.id)
        AS offer_count
"""
_FROM = """
    messages m LEFT JOIN applications a
        ON a.id = m.application_id AND a.user_id = m.user_id AND a.deleted_at IS NULL
"""


def _fields(row: dict[str, Any]) -> dict[str, Any]:
    suggestion = (
        Suggestion(
            type=row["suggestion_type"],
            date=row["suggestion_date"],
            status=row["suggestion_status"],
        )
        if row["suggestion_type"]
        else None
    )
    return {**row, "excerpt": excerpt(row["body_text"]), "suggestion": suggestion}


def list_messages(
    conn: Conn, user_id: int, kind: MessageKind | None = None, hidden: bool = False
) -> list[MessageSummary]:
    """Newest first: the messages shown, or those hidden."""
    rows = conn.execute(
        f"SELECT {_SUMMARY} FROM {_FROM} WHERE m.user_id = %s"
        " AND (%s::text IS NULL OR m.kind = %s) AND (m.hidden_reason IS NOT NULL) = %s"
        " ORDER BY m.received_at DESC, m.id DESC",
        (user_id, kind, kind, hidden),
    ).fetchall()
    return [MessageSummary.model_validate(_fields(row)) for row in rows]


def get_message(conn: Conn, user_id: int, message_id: int) -> Message | None:
    row = conn.execute(
        f"SELECT {_SUMMARY}, m.to_addrs, m.processed_at, m.company_hint, m.linked_by,"
        f" m.llm_call_id FROM {_FROM} WHERE m.user_id = %s AND m.id = %s",
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
    return Message.model_validate(_fields(row) | {"offer_ids": offer_ids})


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
        suggestions=_pending_suggestions(conn, user_id),
    )


def _pending_suggestions(conn: Conn, user_id: int) -> int:
    row = conn.execute(
        f"SELECT count(*) AS n FROM {_FROM} WHERE m.user_id = %s"
        " AND m.suggestion_status = 'pending' AND a.id IS NOT NULL AND m.hidden_reason IS NULL",
        (user_id,),
    ).fetchone()
    return row["n"] if row else 0


# --- the user's decisions --------------------------------------------------------


class SuggestionError(Exception):
    """No pending suggestion, or no application to apply it to."""


def link_application(
    conn: Conn, user_id: int, message_id: int, application_id: int | None, by: LinkedBy = "user"
) -> bool:
    """Tie a message to an application, or untie it with None. Its events go with it:
    left on the first application, they would keep its status. Being tied records
    `message_received`, the one event added without a click. False: no such message or
    application."""
    message = conn.execute(
        "SELECT application_id, subject, received_at, suggestion_status FROM messages"
        " WHERE user_id = %s AND id = %s",
        (user_id, message_id),
    ).fetchone()
    if message is None:
        return False
    if application_id is not None and (
        applications_service.get_application(conn, user_id, application_id) is None
    ):
        return False
    previous: int | None = message["application_id"]
    with conn.transaction():
        conn.execute(
            "UPDATE messages SET application_id = %s, linked_by = %s,"
            " suggestion_status = CASE WHEN %s::bigint IS NULL AND suggestion_status = 'accepted'"
            " THEN 'pending' ELSE suggestion_status END"
            " WHERE user_id = %s AND id = %s",
            (application_id, by if application_id else None, application_id, user_id, message_id),
        )
        if application_id is None:
            conn.execute(
                "DELETE FROM application_events WHERE user_id = %s AND message_id = %s",
                (user_id, message_id),
            )
        else:
            moved = conn.execute(
                "UPDATE application_events SET application_id = %s"
                " WHERE user_id = %s AND message_id = %s",
                (application_id, user_id, message_id),
            ).rowcount
            if not moved:
                applications_service.add_message_event(
                    conn,
                    user_id,
                    application_id,
                    "message_received",
                    message["received_at"].date(),
                    message["subject"],
                    message_id,
                )
        for touched in {previous, application_id} - {None}:
            assert touched is not None
            applications_service.refresh_status(conn, user_id, touched)
    event(
        log,
        "message.linked" if application_id else "message.unlinked",
        user_id=user_id,
        message_id=message_id,
        application_id=application_id,
        previous=previous,
        by=by,
    )
    return True


def accept_suggestion(conn: Conn, user_id: int, message_id: int) -> Message | None:
    """The click that turns a suggestion into an event. Raises `SuggestionError`."""
    message = get_message(conn, user_id, message_id)
    if message is None:
        return None
    suggestion = message.suggestion
    if suggestion is None or suggestion.status != "pending":
        raise SuggestionError("Ce message ne suggère rien à confirmer.")
    if message.application_id is None:
        raise SuggestionError("Rattachez d'abord ce message à une candidature.")
    with conn.transaction():
        applications_service.add_message_event(
            conn,
            user_id,
            message.application_id,
            suggestion.type,
            suggestion.date or message.received_at.date(),
            message.subject,
            message_id,
        )
        conn.execute(
            "UPDATE messages SET suggestion_status = 'accepted' WHERE user_id = %s AND id = %s",
            (user_id, message_id),
        )
    event(
        log,
        "suggestion.accepted",
        user_id=user_id,
        message_id=message_id,
        llm_call_id=message.llm_call_id,
        suggestion=suggestion.type,
        application_id=message.application_id,
    )
    return get_message(conn, user_id, message_id)


def dismiss_suggestion(conn: Conn, user_id: int, message_id: int) -> Message | None:
    """The model's reading overruled: logged, so its accuracy can be read off the log."""
    message = get_message(conn, user_id, message_id)
    if message is None:
        return None
    if message.suggestion is None or message.suggestion.status != "pending":
        raise SuggestionError("Ce message ne suggère rien à écarter.")
    conn.execute(
        "UPDATE messages SET suggestion_status = 'dismissed' WHERE user_id = %s AND id = %s",
        (user_id, message_id),
    )
    event(
        log,
        "suggestion.dismissed",
        user_id=user_id,
        message_id=message_id,
        llm_call_id=message.llm_call_id,
        suggestion=message.suggestion.type,
    )
    return get_message(conn, user_id, message_id)


def set_hidden(conn: Conn, user_id: int, message_id: int, hidden: bool) -> Message | None:
    """Hide a message, or restore it. Restoring a blocked sender's message unblocks the
    sender; restoring one a rule hid sends it to the model at the next sync."""
    row = conn.execute(
        "SELECT from_addr, hidden_reason, category FROM messages WHERE user_id = %s AND id = %s",
        (user_id, message_id),
    ).fetchone()
    if row is None:
        return None
    reason: HiddenReason | None = row["hidden_reason"]
    if hidden and reason is None:
        _set_hidden(conn, user_id, message_id, "user")
        event(log, "message.hidden_by_user", user_id=user_id, message_id=message_id)
    elif not hidden and reason is not None:
        with conn.transaction():
            if reason == "blocked_sender":
                conn.execute(
                    "DELETE FROM blocked_senders WHERE user_id = %s AND address = %s",
                    (user_id, bare_address(row["from_addr"])),
                )
            _set_hidden(conn, user_id, message_id, None)
            if row["category"] is None:
                conn.execute(
                    "UPDATE messages SET processed_at = NULL WHERE user_id = %s AND id = %s"
                    " AND kind = 'message'",
                    (user_id, message_id),
                )
        # Restoring what the model filed as `other` overrules it.
        event(log, "message.restored", user_id=user_id, message_id=message_id, reason=reason)
    return get_message(conn, user_id, message_id)


def block_sender(conn: Conn, user_id: int, message_id: int) -> Message | None:
    """Hide this message and every other one from its sender, now and at each sync,
    without the model."""
    row = conn.execute(
        "SELECT from_addr FROM messages WHERE user_id = %s AND id = %s", (user_id, message_id)
    ).fetchone()
    if row is None:
        return None
    address = bare_address(row["from_addr"])
    with conn.transaction():
        conn.execute(
            "INSERT INTO blocked_senders (user_id, address) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (user_id, address),
        )
        for other in conn.execute(
            "SELECT id, from_addr FROM messages WHERE user_id = %s AND kind = 'message'"
            " AND (hidden_reason IS NULL OR id = %s)",
            (user_id, message_id),
        ).fetchall():
            if bare_address(other["from_addr"]) == address:
                _set_hidden(conn, user_id, other["id"], "blocked_sender")
    event(log, "message.sender_blocked", user_id=user_id, message_id=message_id)
    return get_message(conn, user_id, message_id)

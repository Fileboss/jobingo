"""The one place where an approved action becomes an e-mail. It is the only module that
imports `connectors.smtp`, and nothing that calls the model can reach it."""

import hashlib
import logging
from datetime import date
from email.message import EmailMessage
from email.utils import formataddr, formatdate

from jobingo.config import Settings
from jobingo.connectors.smtp import SendError, SmtpSender
from jobingo.db import Conn
from jobingo.domain.actions import ActionView, SendEmailPayload, payload_hash
from jobingo.hitl.queue import get_action
from jobingo.logs import event
from jobingo.services import documents
from jobingo.services.applications import add_message_event

log = logging.getLogger(__name__)


def _sender(settings: Settings) -> SmtpSender:
    password = settings.mail_smtp_password
    return SmtpSender(
        settings.mail_smtp_host,
        settings.mail_smtp_port,
        settings.mail_smtp_ssl,
        settings.mail_smtp_user,
        password.get_secret_value() if password else "",
    )


def build_message(conn: Conn, user_id: int, payload: SendEmailPayload) -> EmailMessage:
    """The message exactly as the payload says, with each attachment's archived bytes
    checked against the SHA-256 approved. Raises `SendError`."""
    message = EmailMessage()
    message["From"] = (
        formataddr((payload.from_name, payload.from_addr))
        if payload.from_name
        else payload.from_addr
    )
    message["To"] = ", ".join(payload.to)
    if payload.cc:
        message["Cc"] = ", ".join(payload.cc)
    message["Subject"] = payload.subject
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = payload.message_id
    if payload.in_reply_to:
        message["In-Reply-To"] = payload.in_reply_to
    if payload.references:
        message["References"] = " ".join(payload.references)
    message.set_content(payload.body_text)
    for attachment in payload.attachments:
        stored = documents.load(conn, user_id, attachment.document_id)
        if stored is None or hashlib.sha256(stored[1]).hexdigest() != attachment.sha256:
            raise SendError(f"La pièce jointe {attachment.filename} a changé : rien n'est envoyé.")
        message.add_attachment(
            stored[1], maintype="application", subtype="pdf", filename=attachment.filename
        )
    return message


def execute(conn: Conn, settings: Settings, user_id: int, action_id: int) -> ActionView | None:
    """Send one approved action, or say why not. A send problem never raises: it ends in
    the action's status and `error`.

    1. Claim the row (`approved` to `sending`), so a second caller sends nothing.
    2. Check the payload against the hash the user approved.
    3. Build the message, checking each attachment against its archived SHA-256.
    4. Send it, or with `SMTP_DRY_RUN` only keep what would have left; then record it.
    """
    claimed = conn.execute(
        "UPDATE pending_actions SET status = 'sending'"
        " WHERE user_id = %s AND id = %s AND status = 'approved' RETURNING approved_hash",
        (user_id, action_id),
    ).fetchone()
    action = get_action(conn, user_id, action_id)
    if action is None:
        return None
    if claimed is None:
        # A double click or a second tab: nothing is sent twice.
        event(log, "action.claim_lost", user_id=user_id, action_id=action_id, status=action.status)
        return action

    dry_run = settings.smtp_dry_run
    try:
        if payload_hash(action.payload) != claimed["approved_hash"]:
            raise SendError("Le contenu a changé depuis l'approbation : rien n'est envoyé.")
        message = build_message(conn, user_id, action.payload)
        if not dry_run:
            _sender(settings).send(message)
    except SendError as error:
        conn.execute(
            "UPDATE pending_actions SET status = 'failed', error = %s"
            " WHERE user_id = %s AND id = %s",
            (str(error), user_id, action_id),
        )
        event(
            log,
            "action.failed",
            logging.WARNING,
            user_id=user_id,
            action_id=action_id,
            error=str(error)[:300],
        )
        return get_action(conn, user_id, action_id)

    with conn.transaction():
        conn.execute(
            "UPDATE pending_actions SET status = 'sent', sent_at = now(), eml = %s,"
            " dry_run = %s, error = NULL WHERE user_id = %s AND id = %s",
            (bytes(message), dry_run, user_id, action_id),
        )
        # A dry run left nothing: the application's timeline says only what happened.
        if not dry_run and action.application_id is not None:
            add_message_event(
                conn,
                user_id,
                action.application_id,
                "message_sent",
                date.today(),
                action.payload.subject,
                action_id=action_id,
            )
    event(
        log,
        "action.sent",
        user_id=user_id,
        action_id=action_id,
        application_id=action.application_id,
        dry_run=dry_run,
        recipients=len(action.payload.to) + len(action.payload.cc),
        attachments=len(action.payload.attachments),
    )
    return get_action(conn, user_id, action_id)


def load_eml(conn: Conn, user_id: int, action_id: int) -> bytes | None:
    """What left, or would have left in a dry run."""
    row = conn.execute(
        "SELECT eml FROM pending_actions WHERE user_id = %s AND id = %s AND eml IS NOT NULL",
        (user_id, action_id),
    ).fetchone()
    return bytes(row["eml"]) if row else None

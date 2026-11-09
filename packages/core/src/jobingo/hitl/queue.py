"""The approval queue: proposing a send, and the human decisions on it. Nothing here
sends: only `hitl.executor` does, and only an approved action."""

import logging
import uuid
from typing import Any

from jobingo.config import Settings
from jobingo.db import Conn
from jobingo.domain.actions import (
    ActionStatus,
    ActionSummary,
    ActionView,
    Attachment,
    EmailProposal,
    SendEmailPayload,
    canonical_json,
    is_valid_address,
    payload_hash,
)
from jobingo.logs import event
from jobingo.services import documents
from jobingo.services.applications import get_application
from jobingo.services.identity import load_identity

log = logging.getLogger(__name__)


class InvalidAction(Exception):
    """The proposal cannot become an action. The message is shown, in French."""


class NotApprovable(Exception):
    """The action moved on, or the payload on screen is not the stored one."""


_COLUMNS = """
    p.id, p.status, p.payload, p.payload_hash, p.application_id, p.message_id, p.dry_run,
    p.error, p.created_at, p.decided_at, p.sent_at, a.title AS application_title
"""
_FROM = """
    pending_actions p LEFT JOIN applications a
        ON a.id = p.application_id AND a.user_id = p.user_id AND a.deleted_at IS NULL
"""


def _view(row: dict[str, Any]) -> ActionView:
    payload = SendEmailPayload.model_validate(row["payload"])
    return ActionView.model_validate(
        {
            **row,
            "payload": payload,
            "to": payload.to,
            "subject": payload.subject,
            "attachments": len(payload.attachments),
        }
    )


def get_action(conn: Conn, user_id: int, action_id: int) -> ActionView | None:
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM {_FROM} WHERE p.user_id = %s AND p.id = %s",
        (user_id, action_id),
    ).fetchone()
    return _view(row) if row else None


def list_actions(conn: Conn, user_id: int) -> list[ActionSummary]:
    """Waiting for a decision first, then newest first."""
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM {_FROM} WHERE p.user_id = %s"
        " ORDER BY p.status = 'proposed' DESC, p.created_at DESC, p.id DESC",
        (user_id,),
    ).fetchall()
    return [ActionSummary.model_validate(_view(row).model_dump()) for row in rows]


def _source(conn: Conn, user_id: int, message_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT message_id, thread_id, application_id FROM messages"
        " WHERE user_id = %s AND id = %s AND kind = 'message'",
        (user_id, message_id),
    ).fetchone()
    if row is None:
        raise InvalidAction("Message introuvable.")
    return row


def propose_email(
    conn: Conn, settings: Settings, user_id: int, proposal: EmailProposal
) -> ActionView:
    """Freeze a message to send: its recipients, its text, and its attachments rendered
    once and archived. Raises `InvalidAction`."""
    to = [address for address in proposal.to if address]
    cc = [address for address in proposal.cc if address]
    for address in (*to, *cc):
        if not is_valid_address(address):
            raise InvalidAction(f"Adresse invalide : {address}")
    if not to:
        raise InvalidAction("Aucun destinataire.")
    if not proposal.subject.strip() or not proposal.body.strip():
        raise InvalidAction("L'objet et le message ne peuvent pas être vides.")

    application_id = proposal.application_id
    in_reply_to, references = "", []
    if proposal.message_id is not None:
        source = _source(conn, user_id, proposal.message_id)
        in_reply_to = source["message_id"]
        references = list(dict.fromkeys((source["thread_id"], source["message_id"])))
        application_id = application_id or source["application_id"]
    if application_id is not None and get_application(conn, user_id, application_id) is None:
        raise InvalidAction("Candidature introuvable.")
    if proposal.attachments and application_id is None:
        raise InvalidAction("Une pièce jointe vient d'une candidature : rattachez-en une.")

    identity = load_identity(conn, user_id)
    with conn.transaction():
        attachments: list[Attachment] = []
        for wanted in proposal.attachments:
            assert application_id is not None
            try:
                if wanted.kind == "cv":
                    attachments.append(documents.archive_cv(conn, user_id, application_id))
                elif wanted.letter_id is None:
                    raise InvalidAction("Quelle lettre joindre ?")
                else:
                    attachments.append(
                        documents.archive_letter(conn, user_id, application_id, wanted.letter_id)
                    )
            except documents.DocumentError as error:
                raise InvalidAction(str(error)) from None
        payload = SendEmailPayload(
            from_name=identity.name,
            from_addr=settings.mail_from,
            to=to,
            cc=cc,
            subject=proposal.subject.strip(),
            body_text=proposal.body.strip() + "\n",
            in_reply_to=in_reply_to,
            references=references,
            attachments=attachments,
            message_id=f"<{uuid.uuid4()}@jobingo.local>",
        )
        row = conn.execute(
            "INSERT INTO pending_actions"
            " (user_id, kind, payload, payload_hash, application_id, message_id)"
            " VALUES (%s, 'send_email', %s::jsonb, %s, %s, %s) RETURNING id",
            (
                user_id,
                canonical_json(payload),
                payload_hash(payload),
                application_id,
                proposal.message_id,
            ),
        ).fetchone()
    assert row is not None
    event(
        log,
        "action.proposed",
        user_id=user_id,
        action_id=row["id"],
        application_id=application_id,
        message_id=proposal.message_id,
        recipients=len(to) + len(cc),
        attachments=len(attachments),
    )
    view = get_action(conn, user_id, row["id"])
    assert view is not None
    return view


def _set_status(
    conn: Conn, user_id: int, action_id: int, new: ActionStatus, *, among: tuple[str, ...]
) -> bool:
    return bool(
        conn.execute(
            "UPDATE pending_actions SET status = %s, decided_at = now()"
            " WHERE user_id = %s AND id = %s AND status = ANY(%s)",
            (new, user_id, action_id, list(among)),
        ).rowcount
    )


def approve(conn: Conn, user_id: int, action_id: int, seen_hash: str) -> None:
    """Record the approval of the payload the user saw. Raises `NotApprovable` when the
    hash on screen is not the stored one, or the action is no longer waiting."""
    action = get_action(conn, user_id, action_id)
    if action is None:
        raise NotApprovable("Envoi introuvable.")
    if seen_hash != action.payload_hash:
        _refused(user_id, action_id, "stale_preview")
        raise NotApprovable("L'aperçu ne correspond plus à l'envoi : rechargez la page.")
    approved = conn.execute(
        "UPDATE pending_actions SET status = 'approved', approved_hash = %s, decided_at = now()"
        " WHERE user_id = %s AND id = %s AND status = 'proposed'",
        (seen_hash, user_id, action_id),
    ).rowcount
    if not approved:
        _refused(user_id, action_id, f"status_{action.status}")
        raise NotApprovable("Cet envoi n'attend plus de validation.")
    event(log, "action.approved", user_id=user_id, action_id=action_id)


def _refused(user_id: int, action_id: int, reason: str) -> None:
    event(
        log,
        "action.approve_refused",
        logging.WARNING,
        user_id=user_id,
        action_id=action_id,
        reason=reason,
    )


def reject(conn: Conn, user_id: int, action_id: int) -> bool:
    """A proposal turned down, or a failed send given up. Kept, never deleted."""
    rejected = _set_status(conn, user_id, action_id, "rejected", among=("proposed", "failed"))
    if rejected:
        event(log, "action.rejected", user_id=user_id, action_id=action_id)
    return rejected


def retry(conn: Conn, user_id: int, action_id: int) -> bool:
    """A failed send back to approved, with the hash approved then: the executor checks
    the payload against it again."""
    retried = bool(
        conn.execute(
            "UPDATE pending_actions SET status = 'approved', error = NULL"
            " WHERE user_id = %s AND id = %s AND status = 'failed' AND approved_hash IS NOT NULL",
            (user_id, action_id),
        ).rowcount
    )
    if retried:
        event(log, "action.retried", user_id=user_id, action_id=action_id)
    return retried


def proposed_count(conn: Conn, user_id: int) -> int:
    row = conn.execute(
        "SELECT count(*) AS n FROM pending_actions WHERE user_id = %s AND status = 'proposed'",
        (user_id,),
    ).fetchone()
    return row["n"] if row else 0

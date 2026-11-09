from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from jobingo.config import Settings
from jobingo.connectors.mail import MailboxError
from jobingo.domain.mail import MailboxStatus, Message, MessageKind, MessageSummary, SyncReport
from jobingo.services import mail
from jobingo_api.deps import CurrentUser, DbConn, LlmBudget, LlmClient, get_settings
from jobingo_api.llm_errors import refused
from jobingo_api.schemas import Refused

router = APIRouter(prefix="/mail", tags=["mail"])

AppSettings = Annotated[Settings, Depends(get_settings)]


@router.get("/status")
def get_status(user: CurrentUser, conn: DbConn, settings: AppSettings) -> MailboxStatus:
    """The mailbox read, whether it is the local demo server, and each folder's last sync."""
    return mail.status(conn, settings, user.id)


@router.post(
    "/sync",
    response_model=SyncReport,
    responses={502: {"model": Refused, "description": "The mailbox could not be read"}},
)
def sync_mailbox(
    user: CurrentUser, conn: DbConn, settings: AppSettings, client: LlmClient, budget: LlmBudget
) -> SyncReport | JSONResponse:
    """Read the inbox and the alert folder, read-only. LinkedIn alerts are read in code;
    other alerts, and scoring the new offers, need the model. Without it, or when a call
    fails, what was read is kept and the report says what waits."""
    try:
        source = mail.mailbox_from_settings(settings)
        return mail.sync(conn, settings, source, client, budget, user.id)
    except MailboxError as error:
        return refused(502, str(error))


@router.get("/messages")
def list_messages(
    user: CurrentUser, conn: DbConn, kind: MessageKind | None = None, hidden: bool = False
) -> list[MessageSummary]:
    """Newest first: the messages shown, or with `hidden` those a rule, the model or the
    user put aside."""
    return mail.list_messages(conn, user.id, kind, hidden)


_MISSING: dict[int | str, dict[str, Any]] = {404: {"description": "No such message"}}
_NO_SUGGESTION: dict[int | str, dict[str, Any]] = {
    404: {"description": "No such message"},
    409: {"model": Refused, "description": "Nothing to decide, or no application"},
}


def _found(message: Message | None) -> Message:
    if message is None:
        raise HTTPException(status_code=404, detail="Message introuvable")
    return message


@router.get("/messages/{message_id}", responses=_MISSING)
def get_message(message_id: int, user: CurrentUser, conn: DbConn) -> Message:
    return _found(mail.get_message(conn, user.id, message_id))


class LinkRequest(BaseModel):
    # None unties the message, and removes the events it brought.
    application_id: int | None


@router.put(
    "/messages/{message_id}/application",
    responses={404: {"description": "No such message or application"}},
)
def link_application(
    message_id: int, body: LinkRequest, user: CurrentUser, conn: DbConn
) -> Message:
    """Tie the message to an application by hand. Its events move with it."""
    if not mail.link_application(conn, user.id, message_id, body.application_id):
        raise HTTPException(status_code=404, detail="Message ou candidature introuvable")
    return _found(mail.get_message(conn, user.id, message_id))


@router.post(
    "/messages/{message_id}/suggestion/accept",
    response_model=Message,
    responses=_NO_SUGGESTION,
)
def accept_suggestion(message_id: int, user: CurrentUser, conn: DbConn) -> Message | JSONResponse:
    """Record the refusal or the interview the message announces, on its application."""
    try:
        return _found(mail.accept_suggestion(conn, user.id, message_id))
    except mail.SuggestionError as error:
        return refused(409, str(error))


@router.post(
    "/messages/{message_id}/suggestion/dismiss",
    response_model=Message,
    responses=_NO_SUGGESTION,
)
def dismiss_suggestion(message_id: int, user: CurrentUser, conn: DbConn) -> Message | JSONResponse:
    try:
        return _found(mail.dismiss_suggestion(conn, user.id, message_id))
    except mail.SuggestionError as error:
        return refused(409, str(error))


class HiddenRequest(BaseModel):
    hidden: bool


@router.put("/messages/{message_id}/hidden", responses=_MISSING)
def set_hidden(message_id: int, body: HiddenRequest, user: CurrentUser, conn: DbConn) -> Message:
    """Hide or restore. A restored message a rule hid goes to the model at the next sync;
    restoring a blocked sender's message unblocks the sender."""
    return _found(mail.set_hidden(conn, user.id, message_id, body.hidden))


@router.post("/messages/{message_id}/block-sender", responses=_MISSING)
def block_sender(message_id: int, user: CurrentUser, conn: DbConn) -> Message:
    """Hide every message from this sender, now and at each sync, without the model."""
    return _found(mail.block_sender(conn, user.id, message_id))

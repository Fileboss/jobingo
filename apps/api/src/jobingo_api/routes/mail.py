from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

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
    user: CurrentUser, conn: DbConn, kind: MessageKind | None = None
) -> list[MessageSummary]:
    """Newest first."""
    return mail.list_messages(conn, user.id, kind)


@router.get("/messages/{message_id}", responses={404: {"description": "No such message"}})
def get_message(message_id: int, user: CurrentUser, conn: DbConn) -> Message:
    message = mail.get_message(conn, user.id, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Message introuvable")
    return message

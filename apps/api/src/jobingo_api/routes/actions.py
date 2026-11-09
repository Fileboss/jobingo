from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse

from jobingo.config import Settings
from jobingo.domain.actions import ActionSummary, ActionView, Approval, EmailProposal
from jobingo.hitl import executor, queue
from jobingo.services import documents
from jobingo_api.deps import CurrentUser, DbConn, get_settings
from jobingo_api.llm_errors import refused
from jobingo_api.schemas import Refused

router = APIRouter(tags=["actions"])

AppSettings = Annotated[Settings, Depends(get_settings)]

_MISSING = "Envoi introuvable"
_DECISION: dict[int | str, dict[str, Any]] = {
    404: {"description": "No such action"},
    409: {"model": Refused, "description": "The action is not in a state for this"},
}


def _found(action: ActionView | None) -> ActionView:
    if action is None:
        raise HTTPException(status_code=404, detail=_MISSING)
    return action


@router.get("/actions")
def list_actions(user: CurrentUser, conn: DbConn) -> list[ActionSummary]:
    """Waiting for a decision first, then newest first."""
    return queue.list_actions(conn, user.id)


@router.post(
    "/actions",
    status_code=201,
    response_model=ActionView,
    responses={422: {"model": Refused, "description": "The proposal cannot be sent as it is"}},
)
def propose_email(
    body: EmailProposal, user: CurrentUser, conn: DbConn, settings: AppSettings
) -> ActionView | JSONResponse:
    """Freeze a message to send, its attachments rendered and archived. Nothing leaves:
    it waits in the queue for an approval."""
    try:
        return queue.propose_email(conn, settings, user.id, body)
    except queue.InvalidAction as error:
        return refused(422, str(error))


@router.get("/actions/{action_id}", responses={404: {"description": "No such action"}})
def get_action(action_id: int, user: CurrentUser, conn: DbConn) -> ActionView:
    return _found(queue.get_action(conn, user.id, action_id))


@router.post("/actions/{action_id}/approve", response_model=ActionView, responses=_DECISION)
def approve(
    action_id: int, body: Approval, user: CurrentUser, conn: DbConn, settings: AppSettings
) -> ActionView | JSONResponse:
    """Approve the payload shown, by its hash, and hand it to the executor. A failed
    send comes back as `failed` with its reason, not as an error."""
    try:
        queue.approve(conn, user.id, action_id, body.payload_hash)
    except queue.NotApprovable as error:
        if queue.get_action(conn, user.id, action_id) is None:
            raise HTTPException(status_code=404, detail=_MISSING) from None
        return refused(409, str(error))
    return _found(executor.execute(conn, settings, user.id, action_id))


@router.post("/actions/{action_id}/retry", response_model=ActionView, responses=_DECISION)
def retry(
    action_id: int, user: CurrentUser, conn: DbConn, settings: AppSettings
) -> ActionView | JSONResponse:
    """Send a failed action again, as approved: same content, same Message-ID."""
    _found(queue.get_action(conn, user.id, action_id))
    if not queue.retry(conn, user.id, action_id):
        return refused(409, "Seul un envoi en échec se relance.")
    return _found(executor.execute(conn, settings, user.id, action_id))


@router.post("/actions/{action_id}/reject", response_model=ActionView, responses=_DECISION)
def reject(action_id: int, user: CurrentUser, conn: DbConn) -> ActionView | JSONResponse:
    """Turn down a proposal, or give up a failed send. It stays in the record."""
    _found(queue.get_action(conn, user.id, action_id))
    if not queue.reject(conn, user.id, action_id):
        return refused(409, "Cet envoi ne peut plus être refusé.")
    return _found(queue.get_action(conn, user.id, action_id))


@router.get(
    "/actions/{action_id}/eml",
    response_class=Response,
    responses={
        200: {"content": {"message/rfc822": {"schema": {"type": "string", "format": "binary"}}}},
        404: {"description": "Nothing built for this action yet"},
    },
)
def get_eml(action_id: int, user: CurrentUser, conn: DbConn) -> Response:
    """The message as it left, or would have left in a dry run, byte for byte."""
    eml = executor.load_eml(conn, user.id, action_id)
    if eml is None:
        raise HTTPException(status_code=404, detail="Aucun message construit pour cet envoi")
    return Response(content=eml, media_type="message/rfc822")


@router.get(
    "/documents/{document_id}/pdf",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}},
        404: {"description": "No such document"},
    },
)
def get_document(document_id: int, user: CurrentUser, conn: DbConn) -> Response:
    """An archived attachment, exactly as it was sent."""
    stored = documents.load(conn, user.id, document_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Document introuvable")
    filename, content = stored
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )

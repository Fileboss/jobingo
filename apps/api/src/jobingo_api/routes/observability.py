from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from jobingo.config import Settings
from jobingo.domain.observability import (
    CallDetail,
    CallPage,
    CallStatus,
    EventLevel,
    EventPage,
    UsageReport,
)
from jobingo.services import app_log, observability
from jobingo_api.deps import CurrentUser, DbConn, get_settings

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/usage")
def get_usage(
    user: CurrentUser,
    conn: DbConn,
    settings: Annotated[Settings, Depends(get_settings)],
    days: Annotated[int, Query(ge=1, le=90)] = 30,
) -> UsageReport:
    """Calls, tokens, cost and latency over the last `days` days, per task and per day."""
    return observability.usage_report(conn, user.id, settings, days)


@router.get("/calls")
def list_calls(
    user: CurrentUser,
    conn: DbConn,
    task: str | None = None,
    status: CallStatus | None = None,
    before_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> CallPage:
    """Newest first."""
    return observability.list_calls(
        conn, user.id, task=task, status=status, before_id=before_id, limit=limit
    )


@router.get("/calls/{call_id}", responses={404: {"description": "No such call"}})
def get_call(call_id: int, user: CurrentUser, conn: DbConn) -> CallDetail:
    """One call with its prompts, its answer and the events it caused."""
    call = observability.get_call(conn, user.id, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Appel introuvable")
    return call


@router.get("/events")
def list_events(
    user: CurrentUser,
    conn: DbConn,
    level: EventLevel = "DEBUG",
    q: Annotated[str | None, Query(max_length=200)] = None,
    llm_call_id: int | None = None,
    before_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> EventPage:
    """Newest first, at `level` or above."""
    return app_log.list_events(
        conn,
        user.id,
        min_level=level,
        text=q or None,
        llm_call_id=llm_call_id,
        before_id=before_id,
        limit=limit,
    )

from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Response

from jobingo.domain.applications import (
    ApplicationSummary,
    ApplicationView,
    Contact,
    NewApplication,
    NewEvent,
)
from jobingo.services import applications
from jobingo_api.deps import CurrentUser, DbConn

router = APIRouter(tags=["applications"])

_NOT_FOUND = "Candidature introuvable"
_404: dict[int | str, dict[str, Any]] = {404: {"description": "No such application"}}


def _found(view: ApplicationView | None) -> ApplicationView:
    if view is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return view


@router.get("/applications")
def list_applications(user: CurrentUser, conn: DbConn) -> list[ApplicationSummary]:
    """Newest first, each with its status derived from its events."""
    return applications.list_applications(conn, user.id)


@router.post("/applications", status_code=201)
def create_application(
    body: Annotated[NewApplication, Body()], user: CurrentUser, conn: DbConn
) -> ApplicationView:
    """An application with no stored offer: a spontaneous one, or a referral."""
    return applications.create_application(conn, user.id, body)


@router.post("/offers/{offer_id}/application", responses={404: {"description": "No such offer"}})
def apply_to_offer(offer_id: int, user: CurrentUser, conn: DbConn) -> ApplicationView:
    """The offer's application, created on the first call. Applying keeps the offer."""
    view = applications.apply_to_offer(conn, user.id, offer_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    return view


@router.get("/applications/{application_id}", responses=_404)
def get_application(application_id: int, user: CurrentUser, conn: DbConn) -> ApplicationView:
    return _found(applications.get_application(conn, user.id, application_id))


@router.delete("/applications/{application_id}", status_code=204, responses=_404)
def delete_application(application_id: int, user: CurrentUser, conn: DbConn) -> Response:
    """Hidden, not erased: its events stay, for the record."""
    if not applications.delete_application(conn, user.id, application_id):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return Response(status_code=204)


@router.post("/applications/{application_id}/events", status_code=201, responses=_404)
def add_event(
    application_id: int, body: Annotated[NewEvent, Body()], user: CurrentUser, conn: DbConn
) -> ApplicationView:
    """Record what happened. The status follows from the events."""
    return _found(applications.add_event(conn, user.id, application_id, body))


@router.delete("/applications/{application_id}/events/{event_id}", responses=_404)
def remove_event(
    application_id: int, event_id: int, user: CurrentUser, conn: DbConn
) -> ApplicationView:
    return _found(applications.remove_event(conn, user.id, application_id, event_id))


@router.put("/applications/{application_id}/contact", responses=_404)
def set_contact(
    application_id: int, body: Annotated[Contact, Body()], user: CurrentUser, conn: DbConn
) -> ApplicationView:
    return _found(applications.set_contact(conn, user.id, application_id, body))

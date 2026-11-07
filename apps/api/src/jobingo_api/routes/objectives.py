from typing import Annotated

from fastapi import APIRouter, Body

from jobingo.domain.objectives import Objectives
from jobingo.services import objectives
from jobingo.services.objectives import ObjectivesView
from jobingo_api.deps import CurrentUser, DbConn

router = APIRouter(prefix="/objectives", tags=["objectives"])


@router.get("")
def get_objectives(user: CurrentUser, conn: DbConn) -> ObjectivesView:
    """Never saved is the defaults, which filter nothing."""
    return objectives.view(conn, user.id)


@router.put("")
def save_objectives(
    body: Annotated[Objectives, Body()], user: CurrentUser, conn: DbConn
) -> ObjectivesView:
    """The whole document; the offers come back through the saved filters."""
    return objectives.save_objectives(conn, user.id, body)

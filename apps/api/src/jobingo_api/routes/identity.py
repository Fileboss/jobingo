from typing import Annotated

from fastapi import APIRouter, Body, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from jobingo.db import Conn
from jobingo.domain.identity import Identity
from jobingo.services import identity as identity_service
from jobingo.services.photo import InvalidPhotoError
from jobingo_api.deps import CurrentUser, DbConn
from jobingo_api.schemas import Refused

router = APIRouter(prefix="/identity", tags=["identity"])


class IdentityDocument(Identity):
    has_photo: bool


class PhotoUpload(BaseModel):
    data_base64: str


def _document(conn: Conn, user_id: int) -> IdentityDocument:
    identity = identity_service.load_identity(conn, user_id)
    return IdentityDocument(
        **identity.model_dump(), has_photo=identity_service.has_photo(conn, user_id)
    )


@router.get("")
def get_identity(user: CurrentUser, conn: DbConn) -> IdentityDocument:
    """Never saved is all empty, not an error."""
    return _document(conn, user.id)


@router.put("")
def save_identity(
    identity: Annotated[Identity, Body()], user: CurrentUser, conn: DbConn
) -> IdentityDocument:
    identity_service.save_identity(conn, user.id, identity)
    return _document(conn, user.id)


@router.get(
    "/photo",
    response_class=Response,
    responses={
        200: {"content": {"image/jpeg": {"schema": {"type": "string", "format": "binary"}}}},
        404: {"description": "No photo"},
    },
)
def get_photo(user: CurrentUser, conn: DbConn) -> Response:
    photo = identity_service.load_photo(conn, user.id)
    if photo is None:
        return Response(status_code=404)
    return Response(content=bytes(photo), media_type="image/jpeg")


@router.put(
    "/photo",
    response_model=IdentityDocument,
    responses={400: {"model": Refused, "description": "Not a usable JPEG or PNG"}},
)
def save_photo(
    upload: Annotated[PhotoUpload, Body()], user: CurrentUser, conn: DbConn
) -> IdentityDocument | JSONResponse:
    try:
        identity_service.save_photo(conn, user.id, upload.data_base64)
    except InvalidPhotoError as refused:
        return JSONResponse(status_code=400, content=Refused(message=str(refused)).model_dump())
    return _document(conn, user.id)


@router.delete("/photo")
def delete_photo(user: CurrentUser, conn: DbConn) -> IdentityDocument:
    identity_service.remove_photo(conn, user.id)
    return _document(conn, user.id)

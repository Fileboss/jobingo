from typing import Annotated

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from jobingo.domain.cv_diagnostics import CvDiagnostic
from jobingo.domain.cv_document import CvDocument, CvDraft, CvLang, CvView, convert_draft
from jobingo.services import cv_editor
from jobingo.services.cv import document_of, load_cv
from jobingo_api.deps import CurrentUser, DbConn

router = APIRouter(prefix="/cv", tags=["cv"])


class ConvertRequest(BaseModel):
    draft: CvDraft


class SaveRequest(BaseModel):
    draft: CvDraft
    expected_sha256: str | None


class CvConflict(BaseModel):
    current: CvDocument


class CvRejected(BaseModel):
    diagnostics: list[CvDiagnostic]


@router.get("/{lang}")
def get_cv(lang: CvLang, user: CurrentUser, conn: DbConn) -> CvDocument:
    """The CV in both views. A CV never saved is an empty document, not an error."""
    return document_of(load_cv(conn, user.id, lang), lang)


@router.post("/{lang}/convert")
def convert_cv_draft(lang: CvLang, request: Annotated[ConvertRequest, Body()]) -> CvView:
    """Both views and the diagnostics of a draft, without storing anything."""
    return convert_draft(request.draft, lang)


@router.put(
    "/{lang}",
    response_model=CvDocument,
    responses={
        400: {"model": CvRejected, "description": "The draft has a duplicate id"},
        409: {"model": CvConflict, "description": "The stored CV changed since it was loaded"},
    },
)
def save_cv(
    lang: CvLang, request: Annotated[SaveRequest, Body()], user: CurrentUser, conn: DbConn
) -> CvDocument | JSONResponse:
    try:
        return cv_editor.save_cv(conn, user.id, lang, request.draft, request.expected_sha256)
    except cv_editor.CvConflictError as conflict:
        body = CvConflict(current=conflict.current)
        return JSONResponse(status_code=409, content=body.model_dump(mode="json"))
    except cv_editor.CvRejectedError as rejected:
        body = CvRejected(diagnostics=rejected.diagnostics)
        return JSONResponse(status_code=400, content=body.model_dump(mode="json"))

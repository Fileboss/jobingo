from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Response
from fastapi.responses import JSONResponse

from jobingo.domain.cv_draft import DraftChoices, DraftSummary, DraftView
from jobingo.services import cv_drafts
from jobingo.services.cv_page import CvRenderError, OptionUnavailableError
from jobingo.services.cv_proposal import NothingToTailorError, PersonalDataInCvError
from jobingo_api.deps import CurrentUser, DbConn, LlmBudget, LlmClient
from jobingo_api.llm_errors import LLM_RESPONSES, llm_refusal, not_configured, refused
from jobingo_api.schemas import Refused

router = APIRouter(tags=["cv-drafts"])

_NOT_FOUND = "CV adapté introuvable"


_ADAPT_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": Refused, "description": "Nothing to adapt, or contact details in the CV"},
    404: {"description": "No such application"},
    **LLM_RESPONSES,
}


@router.post(
    "/applications/{application_id}/cv-drafts",
    response_model=DraftView,
    status_code=201,
    responses=_ADAPT_RESPONSES,
)
def adapt_cv(
    application_id: int,
    user: CurrentUser,
    conn: DbConn,
    client: LlmClient,
    budget: LlmBudget,
) -> DraftView | JSONResponse:
    """A CV adapted for this application: to its offer, or for a spontaneous one to the
    role, the company and the notes on it. One call, journalled."""
    if client is None:
        return not_configured()
    try:
        draft = cv_drafts.create_draft_for_application(
            conn, client, budget, user.id, "fr", application_id
        )
    except (NothingToTailorError, PersonalDataInCvError) as error:
        return refused(400, str(error))
    except Exception as error:
        answer = llm_refusal(error)
        if answer is None:
            raise
        return answer
    if draft is None:
        raise HTTPException(status_code=404, detail="Candidature introuvable")
    return draft


@router.get("/applications/{application_id}/cv-drafts")
def list_drafts(application_id: int, user: CurrentUser, conn: DbConn) -> list[DraftSummary]:
    """The application's adapted CVs, newest first."""
    return cv_drafts.list_drafts(conn, user.id, application_id)


@router.get("/cv/drafts/{draft_id}", responses={404: {"description": "No such draft"}})
def get_draft(draft_id: int, user: CurrentUser, conn: DbConn) -> DraftView:
    draft = cv_drafts.load_draft(conn, user.id, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return draft


@router.delete(
    "/cv/drafts/{draft_id}", status_code=204, responses={404: {"description": "No such draft"}}
)
def delete_draft(draft_id: int, user: CurrentUser, conn: DbConn) -> Response:
    if not cv_drafts.delete_draft(conn, user.id, draft_id):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return Response(status_code=204)


@router.put(
    "/cv/drafts/{draft_id}/choices",
    response_model=DraftView,
    responses={
        400: {"model": Refused, "description": "An option that cannot be on"},
        404: {"description": "No such draft"},
    },
)
def save_draft_choices(
    draft_id: int, choices: Annotated[DraftChoices, Body()], user: CurrentUser, conn: DbConn
) -> DraftView | JSONResponse:
    try:
        draft = cv_drafts.save_choices(conn, user.id, draft_id, choices)
    except OptionUnavailableError as error:
        return refused(400, str(error))
    if draft is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return draft


@router.get(
    "/cv/drafts/{draft_id}/pdf",
    response_class=Response,
    responses={
        200: {
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
            "headers": {
                "X-Page-Count": {"schema": {"type": "integer"}},
                "X-Missing-Items": {
                    "description": "Selected items cut from the PDF: a panel over its page",
                    "schema": {"type": "integer"},
                },
                "Content-Disposition": {"schema": {"type": "string"}},
            },
        },
        404: {"description": "No such draft"},
        503: {"model": Refused, "description": "The PDF could not be produced"},
    },
)
def get_draft_pdf(draft_id: int, user: CurrentUser, conn: DbConn) -> Response:
    """The PDF of the draft as it stands."""
    try:
        pdf = cv_drafts.render_draft(conn, user.id, draft_id)
    except CvRenderError as failed:
        return refused(503, str(failed))
    if pdf is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return Response(
        content=pdf.rendered.pdf,
        media_type="application/pdf",
        headers={
            "X-Page-Count": str(pdf.rendered.pages),
            "X-Missing-Items": str(pdf.missing_items),
            "Content-Disposition": f'inline; filename="{pdf.filename}"',
        },
    )


@router.get(
    "/cv/drafts/{draft_id}/html",
    response_class=Response,
    responses={
        200: {
            "content": {"text/html": {"schema": {"type": "string"}}},
            "headers": {"Content-Disposition": {"schema": {"type": "string"}}},
        },
        404: {"description": "No such draft"},
    },
)
def get_draft_html(draft_id: int, user: CurrentUser, conn: DbConn) -> Response:
    """The draft as it stands, as one self-contained HTML file to download: for the user
    to adjust before printing, by hand or with another assistant."""
    html = cv_drafts.draft_html(conn, user.id, draft_id)
    if html is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return Response(
        content=html.html,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{html.filename}"'},
    )

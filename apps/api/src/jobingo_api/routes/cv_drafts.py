from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Response
from fastapi.responses import JSONResponse

from jobingo.domain.cv_document import CvLang
from jobingo.domain.cv_draft import DraftChoices, DraftSummary, DraftView, OfferInput
from jobingo.llm.client import LLMUnavailable, LLMValidationError
from jobingo.llm.journal import LLMBudgetExceeded
from jobingo.services import cv_drafts
from jobingo.services.cv_page import CvRenderError, OptionUnavailableError
from jobingo.services.cv_proposal import NothingToTailorError, PersonalDataInCvError
from jobingo_api.deps import CurrentUser, DbConn, LlmBudget, LlmClient
from jobingo_api.schemas import Refused

router = APIRouter(tags=["cv-drafts"])

_NOT_FOUND = "CV adapté introuvable"


def _refused(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content=Refused(message=message).model_dump())


@router.post(
    "/cv/{lang}/drafts",
    response_model=DraftView,
    status_code=201,
    responses={
        400: {"model": Refused, "description": "Nothing to adapt, or contact details in the CV"},
        429: {"model": Refused, "description": "A spending cap is reached"},
        502: {"model": Refused, "description": "The model's answer was unusable"},
        503: {"model": Refused, "description": "No API key, or the API is unavailable"},
    },
)
def create_draft(
    lang: CvLang,
    offer: Annotated[OfferInput, Body()],
    user: CurrentUser,
    conn: DbConn,
    client: LlmClient,
    budget: LlmBudget,
) -> DraftView | JSONResponse:
    """Ask the model which parts of the CV serve this offer. One call, journalled."""
    if client is None:
        return _refused(
            503, "L'IA n'est pas configurée : renseignez ANTHROPIC_API_KEY, puis relancez l'API."
        )
    try:
        return cv_drafts.create_draft(conn, client, budget, user.id, lang, offer)
    except (NothingToTailorError, PersonalDataInCvError) as refused:
        return _refused(400, str(refused))
    except LLMBudgetExceeded as exceeded:
        return _refused(
            429, f"Aucun appel : {exceeded}. Le plafond se règle dans la configuration."
        )
    except LLMUnavailable:
        return _refused(503, "L'API Anthropic ne répond pas. Réessayez dans un instant.")
    except LLMValidationError:
        return _refused(
            502, "La réponse du modèle était inutilisable, même après une relance. Réessayez."
        )


@router.get("/cv/drafts")
def list_drafts(user: CurrentUser, conn: DbConn) -> list[DraftSummary]:
    """Newest first."""
    return cv_drafts.list_drafts(conn, user.id)


@router.get("/cv/drafts/{draft_id}", responses={404: {"description": "No such draft"}})
def get_draft(draft_id: int, user: CurrentUser, conn: DbConn) -> DraftView:
    draft = cv_drafts.load_draft(conn, user.id, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return draft


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
    except OptionUnavailableError as refused:
        return _refused(400, str(refused))
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
        return _refused(503, str(failed))
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

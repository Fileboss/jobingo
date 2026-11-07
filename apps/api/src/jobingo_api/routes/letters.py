from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from jobingo.services import letters
from jobingo.services.letters import LetterSummary, LetterTexts, LetterView
from jobingo_api.deps import CurrentUser, DbConn, LlmBudget, LlmClient
from jobingo_api.llm_errors import LLM_RESPONSES, llm_refusal, not_configured, refused
from jobingo_api.schemas import Refused

router = APIRouter(tags=["letters"])

_NO_APPLICATION = "Candidature introuvable"
_NO_LETTER = "Lettre introuvable"


class CompanyNotes(BaseModel):
    notes: str = Field(max_length=10_000)


@router.put(
    "/applications/{application_id}/company-notes",
    status_code=204,
    responses={404: {"description": "No such application"}},
)
def set_company_notes(
    application_id: int, body: Annotated[CompanyNotes, Body()], user: CurrentUser, conn: DbConn
) -> Response:
    """What the user knows about the company: a source the letter's facts may come from."""
    if not letters.set_company_notes(conn, user.id, application_id, body.notes):
        raise HTTPException(status_code=404, detail=_NO_APPLICATION)
    return Response(status_code=204)


@router.get("/applications/{application_id}/letters")
def list_letters(application_id: int, user: CurrentUser, conn: DbConn) -> list[LetterSummary]:
    return letters.list_letters(conn, user.id, application_id)


@router.post(
    "/applications/{application_id}/letters",
    response_model=LetterView,
    status_code=201,
    responses={
        400: {"model": Refused, "description": "Nothing to write from, or contact details"},
        404: {"description": "No such application"},
        **LLM_RESPONSES,
    },
)
def propose_letter(
    application_id: int, user: CurrentUser, conn: DbConn, client: LlmClient, budget: LlmBudget
) -> LetterView | JSONResponse:
    """One call writes every slot; code checks each one. A refused slot comes back
    empty, with the proposal and the reason beside it."""
    if client is None:
        return not_configured()
    try:
        letter = letters.propose_letter(conn, client, budget, user.id, application_id)
    except letters.LetterNotPossibleError as error:
        return refused(400, str(error))
    except Exception as error:
        answer = llm_refusal(error)
        if answer is None:
            raise
        return answer
    if letter is None:
        raise HTTPException(status_code=404, detail=_NO_APPLICATION)
    return letter


_LETTER_404: dict[int | str, dict[str, Any]] = {404: {"description": "No such letter"}}


@router.get("/letters/{letter_id}", responses=_LETTER_404)
def get_letter(letter_id: int, user: CurrentUser, conn: DbConn) -> LetterView:
    letter = letters.get_letter(conn, user.id, letter_id)
    if letter is None:
        raise HTTPException(status_code=404, detail=_NO_LETTER)
    return letter


@router.put("/letters/{letter_id}/texts", responses=_LETTER_404)
def save_letter_texts(
    letter_id: int, body: Annotated[LetterTexts, Body()], user: CurrentUser, conn: DbConn
) -> LetterView:
    """The user's texts: theirs, so not checked for facts, only for the limits."""
    letter = letters.save_texts(conn, user.id, letter_id, body)
    if letter is None:
        raise HTTPException(status_code=404, detail=_NO_LETTER)
    return letter


@router.get(
    "/letters/{letter_id}/pdf",
    response_class=Response,
    responses={
        200: {
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
            "headers": {
                "X-Page-Count": {"schema": {"type": "integer"}},
                "Content-Disposition": {"schema": {"type": "string"}},
            },
        },
        404: {"description": "No such letter"},
        503: {"model": Refused, "description": "The PDF could not be produced"},
    },
)
def get_letter_pdf(letter_id: int, user: CurrentUser, conn: DbConn) -> Response:
    try:
        pdf = letters.render(conn, user.id, letter_id)
    except letters.LetterRenderError as error:
        return refused(503, str(error))
    if pdf is None:
        raise HTTPException(status_code=404, detail=_NO_LETTER)
    return Response(
        content=pdf.pdf,
        media_type="application/pdf",
        headers={
            "X-Page-Count": str(pdf.pages),
            "Content-Disposition": f'inline; filename="{pdf.filename}"',
        },
    )

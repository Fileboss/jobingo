from typing import Annotated

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse

from jobingo.domain.cv_document import CvLang
from jobingo.domain.cv_draft import DraftSummary, DraftView
from jobingo.domain.offers import IntakeResult, Offer, OfferIntake
from jobingo.services import cv_drafts, offers
from jobingo.services.cv_proposal import NothingToTailorError, PersonalDataInCvError
from jobingo_api.deps import CurrentUser, DbConn, LlmBudget, LlmClient
from jobingo_api.llm_errors import LLM_RESPONSES, llm_refusal, not_configured, refused
from jobingo_api.schemas import Refused

router = APIRouter(prefix="/offers", tags=["offers"])

_NOT_FOUND = "Offre introuvable"


class OfferPage(Offer):
    # The CVs adapted to this offer, newest first.
    drafts: list[DraftSummary]


@router.post(
    "/intake",
    response_model=IntakeResult,
    status_code=201,
    responses={422: {"model": Refused, "description": "No offer in the text"}, **LLM_RESPONSES},
)
def intake_offers(
    body: Annotated[OfferIntake, Body()],
    user: CurrentUser,
    conn: DbConn,
    client: LlmClient,
    budget: LlmBudget,
) -> IntakeResult | JSONResponse:
    """Every offer in a pasted text: an offer, an alert, a digest. One call, journalled.
    A known offer is completed rather than duplicated."""
    if client is None:
        return not_configured()
    try:
        return offers.intake(conn, client, budget, user.id, body.text)
    except offers.NoOfferFoundError as error:
        return refused(422, str(error))
    except Exception as error:
        answer = llm_refusal(error)
        if answer is None:
            raise
        return answer


@router.get("")
def list_offers(user: CurrentUser, conn: DbConn) -> list[Offer]:
    """Newest first."""
    return offers.list_offers(conn, user.id)


@router.get("/{offer_id}", responses={404: {"description": "No such offer"}})
def get_offer(offer_id: int, user: CurrentUser, conn: DbConn) -> OfferPage:
    offer = offers.get_offer(conn, user.id, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    drafts = cv_drafts.list_drafts(conn, user.id, offer_id=offer_id)
    return OfferPage(**offer.model_dump(), drafts=drafts)


@router.post(
    "/{offer_id}/cv-drafts/{lang}",
    response_model=DraftView,
    status_code=201,
    responses={
        400: {"model": Refused, "description": "Nothing to adapt, or contact details in the CV"},
        404: {"description": "No such offer"},
        **LLM_RESPONSES,
    },
)
def adapt_cv_to_offer(
    offer_id: int,
    lang: CvLang,
    user: CurrentUser,
    conn: DbConn,
    client: LlmClient,
    budget: LlmBudget,
) -> DraftView | JSONResponse:
    """A CV adapted to this offer, as `POST /cv/{lang}/drafts` makes it from pasted text."""
    if client is None:
        return not_configured()
    try:
        draft = cv_drafts.create_draft_for_offer(conn, client, budget, user.id, lang, offer_id)
    except (NothingToTailorError, PersonalDataInCvError) as error:
        return refused(400, str(error))
    except Exception as error:
        answer = llm_refusal(error)
        if answer is None:
            raise
        return answer
    if draft is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return draft

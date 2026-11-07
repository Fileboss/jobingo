from typing import Annotated

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from jobingo.domain.cv_document import CvLang
from jobingo.domain.cv_draft import DraftSummary, DraftView
from jobingo.domain.offers import IntakeResult, OfferDecision, OfferIntake
from jobingo.domain.scoring import ScoredOffer, ScoringRun
from jobingo.services import cv_drafts, offer_intake, offers, scoring
from jobingo.services.cv_proposal import NothingToTailorError, PersonalDataInCvError
from jobingo_api.deps import CurrentUser, DbConn, LlmBudget, LlmClient
from jobingo_api.llm_errors import LLM_RESPONSES, llm_refusal, not_configured, refused
from jobingo_api.schemas import Refused

router = APIRouter(prefix="/offers", tags=["offers"])

_NOT_FOUND = "Offre introuvable"


class OfferPage(ScoredOffer):
    # The CVs adapted to this offer, newest first.
    drafts: list[DraftSummary]


class DecisionBody(BaseModel):
    decision: OfferDecision | None


class StaleCount(BaseModel):
    # Offers never scored, or scored on other objectives or another CV version.
    count: int


def _scored(conn: DbConn, user_id: int, offer_id: int) -> ScoredOffer:
    offer = offers.get_offer(conn, user_id, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return ScoredOffer(
        **offer.model_dump(), current_score=scoring.latest_score(conn, user_id, offer_id)
    )


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
    """Every offer in a pasted text: an offer, an alert, a digest. One call to extract,
    then one per offer that passes the filters to score it. A known offer is completed
    rather than duplicated. Offers are kept even when their scoring fails."""
    if client is None:
        return not_configured()
    try:
        return offer_intake.intake_and_score(conn, client, budget, user.id, body.text)
    except offers.NoOfferFoundError as error:
        return refused(422, str(error))
    except Exception as error:
        answer = llm_refusal(error)
        if answer is None:
            raise
        return answer


@router.get("")
def list_offers(user: CurrentUser, conn: DbConn) -> list[ScoredOffer]:
    """Newest first, each with its current score."""
    return scoring.scored_offers(conn, user.id)


@router.get("/stale")
def count_stale_offers(user: CurrentUser, conn: DbConn) -> StaleCount:
    return StaleCount(count=len(scoring.stale_offer_ids(conn, user.id)))


@router.post("/rescore", response_model=ScoringRun, responses=LLM_RESPONSES)
def rescore_stale_offers(
    user: CurrentUser, conn: DbConn, client: LlmClient, budget: LlmBudget
) -> ScoringRun | JSONResponse:
    """Score again every offer never scored, or scored on other objectives or another CV
    version: one call per offer that passes the filters. Stops at the first failure."""
    if client is None:
        return not_configured()
    return scoring.score_many(conn, client, budget, user.id, scoring.stale_offer_ids(conn, user.id))


@router.get("/{offer_id}", responses={404: {"description": "No such offer"}})
def get_offer(offer_id: int, user: CurrentUser, conn: DbConn) -> OfferPage:
    scored = _scored(conn, user.id, offer_id)
    drafts = cv_drafts.list_drafts(conn, user.id, offer_id=offer_id)
    return OfferPage(**scored.model_dump(), drafts=drafts)


@router.post(
    "/{offer_id}/score",
    response_model=ScoredOffer,
    responses={404: {"description": "No such offer"}, **LLM_RESPONSES},
)
def score_offer(
    offer_id: int, user: CurrentUser, conn: DbConn, client: LlmClient, budget: LlmBudget
) -> ScoredOffer | JSONResponse:
    """Filter and score this offer again. An offer the filters eliminate costs no call."""
    if client is None:
        return not_configured()
    try:
        scoring.score_offer(conn, client, budget, user.id, offer_id)
    except scoring.OfferNotFoundError:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from None
    except Exception as error:
        answer = llm_refusal(error)
        if answer is None:
            raise
        return answer
    return _scored(conn, user.id, offer_id)


@router.put("/{offer_id}/decision", responses={404: {"description": "No such offer"}})
def decide_on_offer(
    offer_id: int, body: Annotated[DecisionBody, Body()], user: CurrentUser, conn: DbConn
) -> ScoredOffer:
    """Keep or dismiss an offer, or take the decision back. Scoring never changes it."""
    if not scoring.set_decision(conn, user.id, offer_id, body.decision):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return _scored(conn, user.id, offer_id)


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

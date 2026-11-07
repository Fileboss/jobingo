"""Pasting offers: extract them, then score each one. Kept apart from both services, so
that neither depends on the other."""

from jobingo.db import Conn
from jobingo.domain.offers import IntakeResult
from jobingo.llm.client import LLMClient
from jobingo.llm.journal import Budget
from jobingo.services.offers import get_offer, intake
from jobingo.services.scoring import score_many


def intake_and_score(
    conn: Conn, client: LLMClient, budget: Budget, user_id: int, text: str
) -> IntakeResult:
    """The offers are stored whatever happens to their scoring: a failed scoring is said
    in the result and can be retried from the offer."""
    result = intake(conn, client, budget, user_id, text)
    run = score_many(conn, client, budget, user_id, [offer.id for offer in result.offers])
    refreshed = [get_offer(conn, user_id, offer.id) for offer in result.offers]
    return result.model_copy(
        update={
            "offers": [offer for offer in refreshed if offer is not None],
            "unscored_ids": run.unscored_ids,
            "scoring_error": run.error,
        }
    )

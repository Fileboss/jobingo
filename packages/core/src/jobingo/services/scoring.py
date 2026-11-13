"""Scoring an offer: hard filters in code, then, for an offer that passes, one call
that rates four criteria, then every score computed by code."""

import logging
from typing import Any

from psycopg.types.json import Jsonb

from jobingo.db import Conn
from jobingo.domain.objectives import apply_hard_filters
from jobingo.domain.offers import OfferDecision
from jobingo.domain.profile import parse_cv_markdown
from jobingo.domain.scoring import (
    Criteria,
    OfferScore,
    ScoredOffer,
    ScoringRun,
    fit_score,
    objectives_hash,
    salary_score,
)
from jobingo.llm.client import LLMCallError, LLMClient, LLMUnavailable
from jobingo.llm.journal import Budget, LLMBudgetExceeded, run_task
from jobingo.llm.tasks.score_offer import SCORE_OFFER_TASK, ScoreOfferInput
from jobingo.logs import event
from jobingo.services.cv import load_cv
from jobingo.services.identity import redaction_values
from jobingo.services.objectives import load_objectives
from jobingo.services.offers import get_offer, list_offers

log = logging.getLogger(__name__)

_COLUMNS = """
    id, offer_id, passed_filters, eliminated_by, unknown, criteria, fit_score,
    salary_score, summary, strengths, gaps, weights, llm_call_id, created_at,
    objectives_hash, cv_version
"""


class OfferNotFoundError(Exception):
    pass


def _context(conn: Conn, user_id: int) -> tuple[str, int]:
    """What a score depends on besides the offer: the objectives and the CV version."""
    objectives, _ = load_objectives(conn, user_id)
    stored = load_cv(conn, user_id, "fr")
    return objectives_hash(objectives), stored.version if stored else 0


def _score_of(row: dict[str, Any], context: tuple[str, int]) -> OfferScore:
    stale = (row["objectives_hash"], row["cv_version"]) != context
    return OfferScore.model_validate(row | {"stale": stale})


def latest_scores(conn: Conn, user_id: int) -> dict[int, OfferScore]:
    """The current score of every scored offer, by offer id."""
    context = _context(conn, user_id)
    rows = conn.execute(
        f"""
        SELECT DISTINCT ON (offer_id) {_COLUMNS} FROM offer_scores
        WHERE user_id = %s ORDER BY offer_id, id DESC
        """,  # nosec B608
        (user_id,),
    )
    return {row["offer_id"]: _score_of(row, context) for row in rows}


def latest_score(conn: Conn, user_id: int, offer_id: int) -> OfferScore | None:
    row = conn.execute(
        f"""
        SELECT {_COLUMNS} FROM offer_scores
        WHERE user_id = %s AND offer_id = %s ORDER BY id DESC LIMIT 1
        """,  # nosec B608
        (user_id, offer_id),
    ).fetchone()
    return _score_of(row, _context(conn, user_id)) if row else None


def score_offer(
    conn: Conn, client: LLMClient, budget: Budget, user_id: int, offer_id: int
) -> OfferScore:
    """Filter, then rate if the offer passes. An eliminated offer costs no call.

    Raises `OfferNotFoundError`, and what `run_task` raises: nothing is stored then.
    """
    offer = get_offer(conn, user_id, offer_id)
    if offer is None:
        raise OfferNotFoundError(f"offer {offer_id}")
    objectives, _ = load_objectives(conn, user_id)
    stored = load_cv(conn, user_id, "fr")
    filtered = apply_hard_filters(offer, objectives.hard_filters)

    criteria: Criteria | None = None
    scores: tuple[int | None, int | None] = (None, None)
    summary, strengths, gaps, call_id = "", [], [], None
    if filtered.passed:
        profile = parse_cv_markdown(stored.content if stored else "")
        tags = sorted({tag for item in profile.items for tag in item.tags})
        output, call_id = run_task(
            conn,
            client,
            budget,
            user_id,
            SCORE_OFFER_TASK,
            ScoreOfferInput(
                title=offer.title,
                company_name=offer.company_name,
                location=", ".join(offer.locations),
                contract=offer.contract,
                remote=offer.remote,
                salary_min=offer.salary_min,
                salary_max=offer.salary_max,
                description_md=offer.description_md,
                objectives_preferences=objectives.preferences,
                profile_tags=tags,
            ),
            redaction_values=redaction_values(conn, user_id),
        )
        criteria = Criteria(
            mission=output.mission, stack=output.stack, salary=output.salary, culture=output.culture
        )
        scores = (
            fit_score(criteria, objectives.weights),
            salary_score(criteria, offer),
        )
        summary, strengths, gaps = output.summary, output.strengths, output.gaps

    with conn.transaction():
        row = conn.execute(
            f"""
            INSERT INTO offer_scores (user_id, offer_id, passed_filters, eliminated_by, unknown,
                criteria, fit_score, salary_score, summary, strengths, gaps, weights,
                objectives_hash, cv_version, llm_call_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {_COLUMNS}
            """,  # nosec B608
            (
                user_id,
                offer.id,
                filtered.passed,
                Jsonb(filtered.eliminated_by),
                Jsonb(filtered.unknown),
                Jsonb(criteria.model_dump()) if criteria else None,
                *scores,
                summary,
                Jsonb(strengths),
                Jsonb(gaps),
                Jsonb(objectives.weights.model_dump()),
                objectives_hash(objectives),
                stored.version if stored else 0,
                call_id,
            ),
        ).fetchone()
        conn.execute(
            "UPDATE offers SET state = %s WHERE user_id = %s AND id = %s",
            ("scored" if filtered.passed else "filtered", user_id, offer.id),
        )
    assert row is not None
    event(
        log,
        "offer.scored" if filtered.passed else "offer.filtered",
        user_id=user_id,
        llm_call_id=call_id,
        offer_id=offer.id,
        score=scores[0],
        ratings=criteria.model_dump() if criteria else None,
        weights=objectives.weights.model_dump(),
        eliminated_by=filtered.eliminated_by,
        unknown=filtered.unknown,
    )
    return _score_of(row, _context(conn, user_id))


def set_decision(conn: Conn, user_id: int, offer_id: int, decision: OfferDecision | None) -> bool:
    """The user's call on an offer, which scoring never changes. False: no such offer."""
    updated = conn.execute(
        "UPDATE offers SET decision = %s, updated_at = now() WHERE user_id = %s AND id = %s",
        (decision, user_id, offer_id),
    ).rowcount
    if updated:
        event(log, "offer.decided", user_id=user_id, offer_id=offer_id, decision=decision)
    return bool(updated)


def scored_offers(conn: Conn, user_id: int) -> list[ScoredOffer]:
    """Every offer with its current score and its application, newest first."""
    scores = latest_scores(conn, user_id)
    applied = {
        row["offer_id"]: row["id"]
        for row in conn.execute(
            "SELECT id, offer_id FROM applications"
            " WHERE user_id = %s AND deleted_at IS NULL AND offer_id IS NOT NULL",
            (user_id,),
        )
    }
    return [
        ScoredOffer(
            **offer.model_dump(),
            current_score=scores.get(offer.id),
            application_id=applied.get(offer.id),
        )
        for offer in list_offers(conn, user_id)
    ]


def score_many(
    conn: Conn, client: LLMClient, budget: Budget, user_id: int, offer_ids: list[int]
) -> ScoringRun:
    """Score each offer in turn, stopping at the first failed call."""
    scored: list[int] = []
    for index, offer_id in enumerate(offer_ids):
        try:
            score_offer(conn, client, budget, user_id, offer_id)
        except (LLMCallError, LLMBudgetExceeded) as error:
            if isinstance(error, LLMBudgetExceeded):
                reason = str(error)
            elif isinstance(error, LLMUnavailable):
                reason = error.reason
            else:
                reason = "le modèle n'a pas pu noter l'offre"
            return ScoringRun(scored_ids=scored, unscored_ids=offer_ids[index:], error=reason)
        scored.append(offer_id)
    return ScoringRun(scored_ids=scored, unscored_ids=[], error=None)


def stale_offer_ids(conn: Conn, user_id: int) -> list[int]:
    """Offers never scored, or scored on other objectives or another CV version."""
    scores = latest_scores(conn, user_id)
    return [
        offer.id
        for offer in list_offers(conn, user_id)
        if offer.id not in scores or scores[offer.id].stale
    ]

"""An offer's score: the model rates each criterion from 0 to 10, and code computes
every score shown from those ratings and the user's weights, so a score is always
reproducible and explainable."""

import hashlib
import json
from datetime import datetime

from pydantic import BaseModel, Field

from jobingo.domain.objectives import Objectives, Weights
from jobingo.domain.offers import Offer


class Criteria(BaseModel):
    mission: float = Field(ge=0, le=10)
    stack: float = Field(ge=0, le=10)
    salary: float = Field(ge=0, le=10)
    culture: float = Field(ge=0, le=10)


def _weighted(pairs: list[tuple[float, float]]) -> int:
    total = sum(weight for _, weight in pairs)
    if total <= 0:
        return 0
    return max(0, min(100, round(10 * sum(v * w for v, w in pairs) / total)))


def global_score(criteria: Criteria, weights: Weights) -> int:
    """The weighted average of the four ratings, on 0 to 100."""
    return _weighted(
        [
            (criteria.mission, weights.mission),
            (criteria.stack, weights.stack),
            (criteria.salary, weights.salary),
            (criteria.culture, weights.culture),
        ]
    )


def fit_score(criteria: Criteria, weights: Weights) -> int:
    """How well the job fits, salary aside: many offers state no salary, and the user
    must be able to tell the two apart."""
    return _weighted(
        [
            (criteria.mission, weights.mission),
            (criteria.stack, weights.stack),
            (criteria.culture, weights.culture),
        ]
    )


def salary_score(criteria: Criteria, offer: Offer) -> int | None:
    """None when the offer states no salary: the rating is then a guess, and showing it
    as a score would hide that the salary is unknown."""
    if offer.salary_min is None and offer.salary_max is None:
        return None
    return max(0, min(100, round(criteria.salary * 10)))


def objectives_hash(objectives: Objectives) -> str:
    """What the score depends on in the objectives: a change makes the score stale."""
    canonical = json.dumps(objectives.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class OfferScore(BaseModel):
    id: int
    offer_id: int
    passed_filters: bool
    eliminated_by: list[str]
    unknown: list[str]
    # None when the filters eliminated the offer: no call was made.
    criteria: Criteria | None
    score: int | None
    fit_score: int | None
    salary_score: int | None
    summary: str
    strengths: list[str]
    gaps: list[str]
    weights: Weights
    llm_call_id: int | None
    created_at: datetime
    # The objectives or the CV changed since: scoring again may give another result.
    stale: bool = False


class ScoredOffer(Offer):
    # None: never scored.
    current_score: OfferScore | None


class ScoringRun(BaseModel):
    """What a batch of scorings did. It stops at the first failed call: the next one
    would most likely fail the same way, and each one costs."""

    scored_ids: list[int]
    unscored_ids: list[int]
    error: str | None

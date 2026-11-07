"""The user's objectives, and what their filters make of the offers already received."""

from datetime import datetime

from psycopg.types.json import Jsonb
from pydantic import BaseModel

from jobingo.db import Conn
from jobingo.domain.objectives import Objectives, apply_hard_filters
from jobingo.services.offers import list_offers


class FilteredOffer(BaseModel):
    offer_id: int
    title: str
    company_name: str
    passed: bool
    eliminated_by: list[str]
    unknown: list[str]


class ObjectivesView(BaseModel):
    objectives: Objectives
    updated_at: datetime | None  # None: never saved, the defaults filter nothing
    # Every offer received, through the filters as they are saved.
    offers: list[FilteredOffer]


def load_objectives(conn: Conn, user_id: int) -> tuple[Objectives, datetime | None]:
    row = conn.execute(
        "SELECT hard_filters, weights, preferences, updated_at FROM objectives WHERE user_id = %s",
        (user_id,),
    ).fetchone()
    if row is None:
        return Objectives(), None
    objectives = Objectives.model_validate(
        {
            "hard_filters": row["hard_filters"],
            "weights": row["weights"],
            "preferences": row["preferences"],
        }
    )
    return objectives, row["updated_at"]


def view(conn: Conn, user_id: int) -> ObjectivesView:
    objectives, updated_at = load_objectives(conn, user_id)
    filtered: list[FilteredOffer] = []
    for offer in list_offers(conn, user_id):
        result = apply_hard_filters(offer, objectives.hard_filters)
        filtered.append(
            FilteredOffer(
                offer_id=offer.id,
                title=offer.title,
                company_name=offer.company_name,
                **result.model_dump(),
            )
        )
    return ObjectivesView(objectives=objectives, updated_at=updated_at, offers=filtered)


def save_objectives(conn: Conn, user_id: int, objectives: Objectives) -> ObjectivesView:
    conn.execute(
        """
        INSERT INTO objectives (user_id, hard_filters, weights, preferences)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            hard_filters = EXCLUDED.hard_filters,
            weights = EXCLUDED.weights,
            preferences = EXCLUDED.preferences,
            updated_at = now()
        """,
        (
            user_id,
            Jsonb(objectives.hard_filters.model_dump(mode="json")),
            Jsonb(objectives.weights.model_dump(mode="json")),
            objectives.preferences.strip(),
        ),
    )
    return view(conn, user_id)

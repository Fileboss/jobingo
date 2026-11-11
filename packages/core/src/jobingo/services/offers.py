"""Offers: extracted from pasted text by the model, or read from an alert by code, then
stored and merged by code."""

import logging

from psycopg import sql

from jobingo.db import Conn
from jobingo.domain.linkedin_alert import AlertOffer
from jobingo.domain.offers import (
    ExtractedOffer,
    IntakeResult,
    Offer,
    dedup_key,
    merged_fields,
    unescaped,
    web_url,
)
from jobingo.llm.client import LLMClient
from jobingo.llm.journal import Budget, run_task
from jobingo.llm.tasks.extract_offer import EXTRACT_OFFER_TASK, ExtractOfferInput
from jobingo.logs import event
from jobingo.services.identity import redaction_values

log = logging.getLogger(__name__)

_COLUMNS = """
    id, title, company_name, locations, contract, remote, salary_min, salary_max, url,
    description_md, llm_call_id, message_id, state, decision, created_at, updated_at
"""
# The columns a merge may fill, named here and never taken from the payload.
_MERGEABLE = (
    "locations",
    "contract",
    "remote",
    "url",
    "salary_min",
    "salary_max",
    "description_md",
)


class NoOfferFoundError(Exception):
    """The text holds no offer. The message is shown to the user."""


def get_offer(conn: Conn, user_id: int, offer_id: int) -> Offer | None:
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM offers WHERE user_id = %s AND id = %s", (user_id, offer_id)
    ).fetchone()
    return Offer.model_validate(row) if row else None


def list_offers(conn: Conn, user_id: int) -> list[Offer]:
    """Newest first."""
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM offers WHERE user_id = %s ORDER BY created_at DESC, id DESC",
        (user_id,),
    )
    return [Offer.model_validate(row) for row in rows]


def _store(
    conn: Conn,
    user_id: int,
    extracted: ExtractedOffer,
    call_id: int | None,
    message_id: int | None = None,
) -> tuple[Offer, bool]:
    """The offer, inserted, or merged into the known row with the same key. The second
    value says whether it was merged."""
    key = dedup_key(extracted.company_name, extracted.title, extracted.locations)
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM offers WHERE user_id = %s AND dedup_key = %s",
        (user_id, key),
    ).fetchone()
    if row is not None:
        existing = Offer.model_validate(row)
        updates = merged_fields(existing, extracted)
        if updates:
            assignments = sql.SQL(", ").join(
                sql.SQL("{} = {}").format(sql.Identifier(name), sql.Placeholder(name))
                for name in _MERGEABLE
                if name in updates
            )
            conn.execute(
                sql.SQL(
                    "UPDATE offers SET {}, llm_call_id = COALESCE(%(call)s, llm_call_id),"
                    " updated_at = now() WHERE user_id = %(user)s AND id = %(id)s"
                ).format(assignments),
                {**updates, "call": call_id, "user": user_id, "id": existing.id},
            )
        event(
            log,
            "offer.merged",
            user_id=user_id,
            llm_call_id=call_id,
            offer_id=existing.id,
            fields=sorted(updates),
        )
        merged = get_offer(conn, user_id, existing.id)
        assert merged is not None
        return merged, True

    inserted = conn.execute(
        """
        INSERT INTO offers (user_id, title, company_name, locations, contract, remote,
            salary_min, salary_max, url, description_md, dedup_key, llm_call_id, message_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            user_id,
            extracted.title,
            extracted.company_name,
            extracted.locations,
            extracted.contract,
            extracted.remote,
            extracted.salary_min,
            extracted.salary_max,
            web_url(extracted.url),
            extracted.description_md,
            key,
            call_id,
            message_id,
        ),
    ).fetchone()
    assert inserted is not None
    event(
        log,
        "offer.created",
        user_id=user_id,
        llm_call_id=call_id,
        offer_id=inserted["id"],
        message_id=message_id,
    )
    offer = get_offer(conn, user_id, inserted["id"])
    assert offer is not None
    return offer, False


def intake(
    conn: Conn,
    client: LLMClient,
    budget: Budget,
    user_id: int,
    text: str,
    message_id: int | None = None,
) -> IntakeResult:
    """Every offer in `text`, stored or merged. One call, journalled; the candidate's
    name, e-mail and phone are redacted from the text before it, so the stored
    description holds none of them either. `message_id` is the alert it came in.

    Raises `NoOfferFoundError`, and what `run_task` raises.
    """
    output, call_id = run_task(
        conn,
        client,
        budget,
        user_id,
        EXTRACT_OFFER_TASK,
        ExtractOfferInput(text=text),
        redaction_values=redaction_values(conn, user_id),
    )
    if not output.offers:
        event(log, "offer.none_found", user_id=user_id, llm_call_id=call_id)
        raise NoOfferFoundError("Aucune offre d'emploi n'a été trouvée dans ce texte.")
    offers: list[Offer] = []
    merged: list[int] = []
    with conn.transaction():
        for extracted in output.offers:
            offer, was_merged = _store(conn, user_id, unescaped(extracted), call_id, message_id)
            if offer.id in {known.id for known in offers}:
                continue  # the same offer twice in one text
            offers.append(offer)
            if was_merged:
                merged.append(offer.id)
    event(
        log,
        "offer.extracted",
        user_id=user_id,
        llm_call_id=call_id,
        offers=len(offers),
        merged=len(merged),
        # What the model left empty is what the filters will treat as unknown.
        missing=sorted(
            {
                name
                for extracted in output.offers
                for name in ("company_name", "locations", "contract", "remote", "salary_min")
                if not getattr(extracted, name)
            }
        ),
    )
    return IntakeResult(offers=offers, merged_ids=merged, llm_call_id=call_id)


def store_alert_offers(
    conn: Conn, user_id: int, cards: list[AlertOffer], message_id: int
) -> list[Offer]:
    """The offers of an alert read in code: no call. A known offer is completed, never
    overwritten, so an alert cannot thin out an offer pasted in full."""
    offers: list[Offer] = []
    with conn.transaction():
        for card in cards:
            extracted = ExtractedOffer(
                title=card.title,
                company_name=card.company_name,
                locations=[card.location] if card.location else [],
                url=card.url,
            )
            offer, _ = _store(conn, user_id, extracted, None, message_id)
            if offer.id not in {known.id for known in offers}:
                offers.append(offer)
    return offers

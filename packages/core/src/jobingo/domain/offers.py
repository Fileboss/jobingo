"""Job offers: what an extraction yields, how the same offer from two sources becomes one
row, and which URLs may become a link."""

import hashlib
import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

# The vocabulary the objectives' filters are written in. Free text such as « CDD de
# 12 mois » would make a filter on a known value fail for the wrong reason.
type Contract = Literal["CDI", "CDD", "freelance", "stage", "alternance", "interim", ""]
type Remote = Literal["sur site", "hybride", "remote", ""]


class ExtractedOffer(BaseModel):
    """One offer as `extract_offer` reads it from pasted text."""

    title: str
    company_name: str = ""
    location: str = ""
    contract: Contract = ""
    remote: Remote = ""
    salary_min: int | None = None
    salary_max: int | None = None
    url: str | None = None
    description_md: str = ""


type OfferState = Literal["new", "scored", "filtered"]
type OfferDecision = Literal["shortlisted", "dismissed"]


class Offer(BaseModel):
    id: int
    title: str
    company_name: str
    location: str
    contract: Contract
    remote: Remote
    salary_min: int | None
    salary_max: int | None
    url: str | None
    description_md: str
    # The extraction that created the offer, and the last one that completed it.
    llm_call_id: int | None
    # Set by scoring: not scored yet, scored, or eliminated by the hard filters.
    state: OfferState
    # Set by the user only; scoring never changes it.
    decision: OfferDecision | None
    created_at: datetime
    updated_at: datetime


class OfferIntake(BaseModel):
    text: str = Field(min_length=1, max_length=50_000)


class IntakeResult(BaseModel):
    """The offers the text held: new ones, and known ones completed by it."""

    offers: list[Offer]
    merged_ids: list[int]
    llm_call_id: int
    # Offers stored but not scored, because a scoring call failed, and why.
    unscored_ids: list[int] = []
    scoring_error: str | None = None


_WEB_SCHEMES = ("http", "https")


def web_url(url: str | None) -> str | None:
    """`url` if it is an http(s) address, None otherwise.

    An offer's URL comes from text the user did not write, through the model, and is
    shown as a link: a `javascript:` URL would run script on the app's origin."""
    if not url:
        return None
    url = url.strip()
    if any(char.isspace() or ord(char) < 32 for char in url):
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme.lower() not in _WEB_SCHEMES or not parsed.netloc:
        return None
    return url


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def dedup_key(company_name: str, title: str, location: str) -> str:
    """The same offer received twice, or through two channels, is one row."""
    normalized = "|".join(
        _SLUG_RE.sub("-", value.strip().lower()).strip("-")
        for value in (company_name, title, location)
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def unescaped(extracted: ExtractedOffer) -> ExtractedOffer:
    """The model read the text with `<` and `>` escaped and copies what it read: store
    what the offer actually says."""

    def plain(value: str) -> str:
        return value.replace("&lt;", "<").replace("&gt;", ">")

    return extracted.model_copy(
        update={
            name: plain(getattr(extracted, name))
            for name in ("title", "company_name", "location", "description_md")
        }
    )


def merged_fields(existing: Offer, incoming: ExtractedOffer) -> dict[str, object]:
    """What a second source adds to a known offer. Fields are filled when empty, never
    overwritten, so a thin alert cannot erase a richer source. The description is the
    exception: the longer one wins, since pasting the full text is how a title-only
    alert gets completed."""
    updates: dict[str, object] = {}
    if not existing.contract and incoming.contract:
        updates["contract"] = incoming.contract
    if not existing.remote and incoming.remote:
        updates["remote"] = incoming.remote
    url = web_url(incoming.url)
    if existing.url is None and url:
        updates["url"] = url
    if existing.salary_min is None and incoming.salary_min is not None:
        updates["salary_min"] = incoming.salary_min
    if existing.salary_max is None and incoming.salary_max is not None:
        updates["salary_max"] = incoming.salary_max
    if len(incoming.description_md.strip()) > len(existing.description_md.strip()):
        updates["description_md"] = incoming.description_md
    return updates

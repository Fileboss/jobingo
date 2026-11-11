"""What the user is looking for. The hard filters and the weights are applied by code;
the preferences are free text the model reads to rate an offer."""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from jobingo.domain.offers import Contract, Offer, Remote
from jobingo.domain.text import fold

Term = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Weight = Annotated[float, Field(ge=0, le=5)]


class HardFilters(BaseModel):
    """An empty list or a None filters nothing."""

    contracts: list[Contract] = Field(default=[], max_length=10)
    remote: list[Remote] = Field(default=[], max_length=10)
    # Matched as a part of one of the offer's cities: « Lyon » keeps « Lyon 3e ».
    locations: list[Term] = Field(default=[], max_length=30)
    salary_min_eur: int | None = Field(default=None, ge=0, le=1_000_000)
    # Matched in the title and the description.
    excluded_keywords: list[Term] = Field(default=[], max_length=50)
    excluded_companies: list[Term] = Field(default=[], max_length=50)


class Weights(BaseModel):
    """How much each of the model's ratings counts in the fit score. The salary has its
    own score, so no weight: a weight stored before that is ignored on reading."""

    mission: Weight = 1
    stack: Weight = 1
    culture: Weight = 1


class Objectives(BaseModel):
    hard_filters: HardFilters = HardFilters()
    weights: Weights = Weights()
    preferences: str = Field(default="", max_length=4000)


class FilterResult(BaseModel):
    passed: bool
    # Why the offer is eliminated, in French for the screen.
    eliminated_by: list[str]
    # What a filter could not check because the offer does not say: never eliminating.
    unknown: list[str]


def _norm(value: str) -> str:
    return " ".join(fold(value).split())


def apply_hard_filters(offer: Offer, filters: HardFilters) -> FilterResult:
    """A filter eliminates only on a known value that fails it. An offer that does not
    state its contract is not dropped by a contract filter, it is flagged: an alert
    carries little more than a title, and eliminating on « unknown » would discard a
    whole channel. Comparisons ignore case and accents."""
    eliminated: list[str] = []
    unknown: list[str] = []

    if filters.contracts:
        if not offer.contract:
            unknown.append("contrat")
        elif offer.contract not in filters.contracts:
            eliminated.append(f"contrat non retenu : {offer.contract}")

    if filters.remote:
        if not offer.remote:
            unknown.append("télétravail")
        elif offer.remote not in filters.remote:
            eliminated.append(f"télétravail non retenu : {offer.remote}")

    if filters.locations:
        # One city the user accepts is enough: « Paris ou Toulouse » passes « Toulouse ».
        cities = [city for city in offer.locations if city.strip()]
        if not cities:
            unknown.append("lieu")
        elif not any(_norm(place) in _norm(city) for place in filters.locations for city in cities):
            eliminated.append(f"lieu non retenu : {', '.join(cities)}")

    if filters.salary_min_eur is not None:
        # The top of the range: an offer that may reach the minimum stays.
        stated = offer.salary_max if offer.salary_max is not None else offer.salary_min
        if stated is None:
            unknown.append("salaire")
        elif stated < filters.salary_min_eur:
            minimum = f"{filters.salary_min_eur:,}".replace(",", "\u202f")
            eliminated.append(f"salaire sous {minimum} €")

    text = _norm(f"{offer.title}\n{offer.description_md}")
    for keyword in filters.excluded_keywords:
        if _norm(keyword) in text:
            eliminated.append(f"mot-clé exclu : {keyword}")

    for company in filters.excluded_companies:
        if offer.company_name and _norm(company) == _norm(offer.company_name):
            eliminated.append(f"entreprise exclue : {company}")

    return FilterResult(passed=not eliminated, eliminated_by=eliminated, unknown=unknown)

"""The objectives: hard filters applied by code, and their preview on received offers."""

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from jobingo.domain.objectives import HardFilters, apply_hard_filters
from jobingo.domain.offers import ExtractedOffer, Offer
from jobingo.llm.fake import FakeLLMClient
from jobingo.llm.tasks.extract_offer import ExtractOfferOutput

NOW = datetime(2026, 11, 7, tzinfo=UTC)


def _offer(**fields: Any) -> Offer:
    base: dict[str, Any] = {
        "id": 1,
        "title": "Ingénieur backend",
        "company_name": "Stratus",
        "location": "Lyon 3e",
        "contract": "CDI",
        "remote": "hybride",
        "salary_min": 55000,
        "salary_max": 62000,
        "url": None,
        "description_md": "API en Python.",
        "llm_call_id": None,
        "message_id": None,
        "state": "new",
        "decision": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    return Offer.model_validate(base | fields)


def test_no_filter_eliminates_nothing():
    result = apply_hard_filters(_offer(), HardFilters())
    assert (result.passed, result.eliminated_by, result.unknown) == (True, [], [])


@pytest.mark.parametrize(
    ("filters", "offer", "reason"),
    [
        (HardFilters(contracts=["CDI"]), {"contract": "CDD"}, "contrat non retenu : CDD"),
        (HardFilters(remote=["remote"]), {}, "télétravail non retenu : hybride"),
        (HardFilters(locations=["Paris"]), {}, "lieu non retenu : Lyon 3e"),
        (HardFilters(salary_min_eur=65000), {}, "salaire sous 65\u202f000 €"),
        (HardFilters(excluded_keywords=["python"]), {}, "mot-clé exclu : python"),
        (HardFilters(excluded_companies=["STRATUS "]), {}, "entreprise exclue : STRATUS"),
    ],
)
def test_a_known_value_that_fails_eliminates(
    filters: HardFilters, offer: dict[str, Any], reason: str
):
    result = apply_hard_filters(_offer(**offer), filters)
    assert not result.passed
    assert result.eliminated_by == [reason]


def test_an_unknown_value_is_flagged_never_eliminating():
    offer = _offer(contract="", remote="", location="", salary_min=None, salary_max=None)
    filters = HardFilters(
        contracts=["CDI"], remote=["remote"], locations=["Lyon"], salary_min_eur=60000
    )
    result = apply_hard_filters(offer, filters)
    assert result.passed
    assert result.unknown == ["contrat", "télétravail", "lieu", "salaire"]


def test_places_and_keywords_ignore_case_and_accents():
    offer = _offer(location="Saint-Étienne", description_md="Mission en régie.")
    assert apply_hard_filters(offer, HardFilters(locations=["saint-etienne"])).passed
    result = apply_hard_filters(offer, HardFilters(excluded_keywords=["REGIE"]))
    assert result.eliminated_by == ["mot-clé exclu : REGIE"]


def test_the_top_of_the_salary_range_counts():
    assert apply_hard_filters(_offer(), HardFilters(salary_min_eur=60000)).passed
    only_low = _offer(salary_max=None)
    assert not apply_hard_filters(only_low, HardFilters(salary_min_eur=60000)).passed


# --- Through the API ---------------------------------------------------------------------


def test_never_saved_objectives_are_the_defaults(client: TestClient):
    view = client.get("/api/objectives").json()
    assert view["updated_at"] is None
    assert view["objectives"]["weights"] == {
        "mission": 1,
        "stack": 1,
        "salary": 1,
        "culture": 1,
    }
    assert view["offers"] == []


def test_saved_filters_show_which_offers_pass(client: TestClient):
    fake = FakeLLMClient()
    client.app.state.llm_client = fake  # type: ignore[attr-defined]
    fake.queue(
        "extract_offer",
        ExtractOfferOutput(
            offers=[
                ExtractedOffer(title="Data engineer", company_name="Plume", contract="CDI"),
                ExtractedOffer(title="Développeur Java", company_name="Banque", contract="CDD"),
                ExtractedOffer(title="Tech Lead", company_name="Voltéo"),
            ]
        ),
    )
    client.post("/api/offers/intake", json={"text": "Trois offres."})

    saved = client.put(
        "/api/objectives",
        json={
            "hard_filters": {"contracts": ["CDI"], "excluded_keywords": ["java"]},
            "weights": {"mission": 2, "stack": 2, "salary": 1, "culture": 0.5},
            "preferences": "  Plateformes de données, en Python.  ",
        },
    ).json()

    assert saved["updated_at"] is not None
    assert saved["objectives"]["preferences"] == "Plateformes de données, en Python."
    by_title = {offer["title"]: offer for offer in saved["offers"]}
    assert by_title["Data engineer"]["passed"]
    assert by_title["Développeur Java"]["eliminated_by"] == [
        "contrat non retenu : CDD",
        "mot-clé exclu : java",
    ]
    assert by_title["Tech Lead"]["passed"]
    assert by_title["Tech Lead"]["unknown"] == ["contrat"]
    assert client.get("/api/objectives").json() == saved


@pytest.mark.parametrize(
    "body",
    [
        {"hard_filters": {"contracts": ["permanent"]}},
        {"weights": {"mission": 9}},
        {"hard_filters": {"salary_min_eur": -1}},
        {"preferences": "x" * 4001},
    ],
)
def test_out_of_range_objectives_are_refused(client: TestClient, body: dict[str, Any]):
    assert client.put("/api/objectives", json=body).status_code == 422

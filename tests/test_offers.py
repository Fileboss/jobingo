"""Offers pasted as text: extracted by the model, stored, merged and kept safe by code."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from jobingo.domain.offers import ExtractedOffer, web_url
from jobingo.llm.fake import FakeLLMClient
from jobingo.llm.tasks.extract_offer import ExtractOfferOutput

FIXTURE = (Path(__file__).parent / "fixtures" / "cv.fr.md").read_text(encoding="utf-8")
DIGEST = "Nouvelles offres :\n1. Data engineer — Plume Énergie — Lyon\n2. Tech Lead — Voltéo"


def _offers(*offers: ExtractedOffer) -> ExtractOfferOutput:
    return ExtractOfferOutput(offers=list(offers))


DATA = ExtractedOffer(title="Data engineer", company_name="Plume Énergie", locations=["Lyon"])
LEAD = ExtractedOffer(
    title="Tech Lead", company_name="Voltéo", contract="CDI", url="javascript:alert(1)"
)


@pytest.fixture
def fake(client: TestClient) -> FakeLLMClient:
    fake = FakeLLMClient()
    client.app.state.llm_client = fake  # type: ignore[attr-defined]
    return fake


def _intake(client: TestClient, fake: FakeLLMClient, answer: Any, text: str = DIGEST) -> Any:
    fake.queue("extract_offer", answer)
    return client.post("/api/offers/intake", json={"text": text})


def test_a_digest_gives_one_offer_per_position(client: TestClient, fake: FakeLLMClient):
    response = _intake(client, fake, _offers(DATA, LEAD))

    assert response.status_code == 201
    result = response.json()
    assert [o["title"] for o in result["offers"]] == ["Data engineer", "Tech Lead"]
    assert result["merged_ids"] == []
    assert result["offers"][1]["url"] is None  # not a web address: never a link
    listed = client.get("/api/offers").json()
    assert {o["id"] for o in listed} == {o["id"] for o in result["offers"]}
    assert all(o["llm_call_id"] == result["llm_call_id"] for o in listed)


def test_the_same_offer_again_is_completed_not_duplicated(client: TestClient, fake: FakeLLMClient):
    [first] = _intake(client, fake, _offers(DATA)).json()["offers"]
    richer = DATA.model_copy(
        update={
            "title": "Data Engineer (H/F)".removesuffix(" (H/F)"),
            "contract": "CDI",
            "salary_min": 55000,
            "description_md": "Pipelines Airflow et entrepôt PostgreSQL.",
            "url": "https://plume.example/offres/42",
        }
    )
    thinner = DATA.model_copy(update={"contract": "CDD", "description_md": "Court."})

    second = _intake(client, fake, _offers(richer)).json()
    third = _intake(client, fake, _offers(thinner)).json()

    assert second["merged_ids"] == [first["id"]] == third["merged_ids"]
    [offer] = client.get("/api/offers").json()
    assert offer["contract"] == "CDI"  # filled once, never overwritten
    assert offer["salary_min"] == 55000
    assert offer["description_md"] == "Pipelines Airflow et entrepôt PostgreSQL."
    assert offer["url"] == "https://plume.example/offres/42"


def test_a_second_source_adds_the_cities_it_names(client: TestClient, fake: FakeLLMClient):
    alert = ExtractedOffer(title="Ingénieur IA", company_name="Pivolo", locations=["Nantes"])
    [first] = _intake(client, fake, _offers(alert)).json()["offers"]
    full = alert.model_copy(update={"locations": ["Nantes", "Bordeaux", "nantes"]})

    second = _intake(client, fake, _offers(full)).json()

    assert second["merged_ids"] == [first["id"]]
    [offer] = client.get("/api/offers").json()
    assert offer["locations"] == ["Nantes", "Bordeaux"]


def test_the_candidate_is_redacted_before_the_call(client: TestClient, fake: FakeLLMClient):
    client.put(
        "/api/identity",
        json={
            "name": "Alex Moreau",
            "email": "alex@example.org",
            "phone": "",
            "address": "",
            "linkedin": "",
            "github": "",
        },
    )
    _intake(client, fake, _offers(DATA), text="Bonjour Alex Moreau, voici une offre.")
    task, prompt = fake.prompts[0]
    assert task == "extract_offer"
    assert "Alex" not in prompt.user
    assert "[CANDIDAT]" in prompt.user


def test_escaped_text_is_stored_as_the_offer_says(client: TestClient, fake: FakeLLMClient):
    escaped = DATA.model_copy(update={"description_md": "Salaire &lt; 60 k€ &gt; 50 k€"})
    [offer] = _intake(client, fake, _offers(escaped)).json()["offers"]
    assert offer["description_md"] == "Salaire < 60 k€ > 50 k€"


def test_a_text_without_offer_is_refused(client: TestClient, fake: FakeLLMClient):
    response = _intake(client, fake, _offers())
    assert response.status_code == 422
    assert response.json()["message"].startswith("Aucune offre")


def test_without_a_key_nothing_is_called(client: TestClient):
    client.app.state.llm_client = None  # type: ignore[attr-defined]
    response = client.post("/api/offers/intake", json={"text": DIGEST})
    assert response.status_code == 503


@pytest.mark.parametrize(
    ("url", "kept"),
    [
        ("https://plume.example/offre", True),
        ("http://plume.example", True),
        ("javascript:alert(1)", False),
        ("data:text/html,x", False),
        ("https://plume.example/a b", False),
        ("plume.example/offre", False),
    ],
)
def test_only_web_addresses_become_links(url: str, kept: bool):
    assert (web_url(url) is not None) is kept

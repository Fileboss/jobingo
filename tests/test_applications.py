"""Applications: the status is derived from the events, never written."""

from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from jobingo.domain.applications import (
    ApplicationEvent,
    EventType,
    derive_status,
    next_follow_up,
    tone,
)
from jobingo.domain.offers import ExtractedOffer
from jobingo.llm.fake import FakeLLMClient
from jobingo.llm.tasks.extract_offer import ExtractOfferOutput

NOW = datetime(2026, 11, 7, tzinfo=UTC)


def _events(*steps: tuple[EventType, str]) -> list[ApplicationEvent]:
    return [
        ApplicationEvent(
            id=n, type=kind, occurred_at=date.fromisoformat(day), note="", created_at=NOW
        )
        for n, (kind, day) in enumerate(steps, start=1)
    ]


@pytest.mark.parametrize(
    ("steps", "status"),
    [
        ((), "a_postuler"),
        ((("note", "2026-11-01"),), "a_postuler"),
        ((("applied", "2026-11-01"),), "postule"),
        ((("applied", "2026-11-01"), ("message_received", "2026-11-03")), "en_echange"),
        ((("interview_scheduled", "2026-11-05"), ("applied", "2026-11-01")), "entretien"),
        ((("applied", "2026-11-01"), ("rejected", "2026-11-04")), "cloture"),
        # A late automated mail neither reopens nor takes an interview back a step.
        ((("rejected", "2026-11-04"), ("message_received", "2026-11-06")), "cloture"),
        ((("interview_done", "2026-11-04"), ("message_sent", "2026-11-05")), "entretien"),
    ],
)
def test_the_status_follows_the_events_in_date_order(
    steps: tuple[tuple[EventType, str], ...], status: str
):
    assert derive_status(_events(*steps)) == status


def test_a_follow_up_is_due_a_week_after_applying_if_nothing_happened():
    assert next_follow_up(_events(("applied", "2026-11-01"))) == date(2026, 11, 8)
    answered = _events(("applied", "2026-11-01"), ("message_received", "2026-11-02"))
    assert next_follow_up(answered) is None
    assert next_follow_up(_events(("applied", "2026-11-01"), ("note", "2026-11-03"))) == date(
        2026, 11, 8
    )


def test_an_interview_done_is_at_the_end():
    events = _events(("applied", "2026-11-01"), ("interview_done", "2026-11-05"))
    assert tone(derive_status(events), events) == "final"
    assert tone("postule", _events(("applied", "2026-11-01"))) == "active"


# --- Through the API -----------------------------------------------------------------------


@pytest.fixture
def offer_id(client: TestClient) -> int:
    fake = FakeLLMClient()
    client.app.state.llm_client = fake  # type: ignore[attr-defined]
    fake.queue(
        "extract_offer",
        ExtractOfferOutput(offers=[ExtractedOffer(title="Data engineer", company_name="Plume")]),
    )
    [offer] = client.post("/api/offers/intake", json={"text": "Une offre."}).json()["offers"]
    return offer["id"]


def test_applying_to_an_offer_creates_one_application_and_keeps_the_offer(
    client: TestClient, offer_id: int
):
    first = client.post(f"/api/offers/{offer_id}/application").json()
    again = client.post(f"/api/offers/{offer_id}/application").json()

    assert first["id"] == again["id"]
    assert (first["title"], first["company_name"], first["status"]) == (
        "Data engineer",
        "Plume",
        "a_postuler",
    )
    offer = client.get(f"/api/offers/{offer_id}").json()
    assert offer["decision"] == "shortlisted"
    assert offer["application_id"] == first["id"]
    assert len(client.get("/api/applications").json()) == 1


def test_events_move_the_status_and_removing_one_moves_it_back(client: TestClient, offer_id: int):
    app_id = client.post(f"/api/offers/{offer_id}/application").json()["id"]

    def add(kind: str, day: str, note: str = "") -> Any:
        response = client.post(
            f"/api/applications/{app_id}/events",
            json={"type": kind, "occurred_at": day, "note": note},
        )
        assert response.status_code == 201, response.text
        return response.json()

    applied = add("applied", "2026-11-02")
    assert applied["status"] == "postule"
    assert applied["follow_up_on"] == "2026-11-09"
    interview = add("interview_scheduled", "2026-11-06", "Visio avec l'équipe data")

    assert interview["status"] == "entretien"
    assert interview["follow_up_on"] is None
    assert interview["events"][0]["note"] == "Visio avec l'équipe data"
    newest = interview["events"][0]["id"]
    back = client.delete(f"/api/applications/{app_id}/events/{newest}").json()
    assert back["status"] == "postule"
    [listed] = client.get("/api/applications").json()
    assert listed["status"] == "postule"
    assert listed["last_event"]["type"] == "applied"


def test_a_manual_application_has_no_offer(client: TestClient):
    created = client.post(
        "/api/applications", json={"title": "Candidature spontanée", "company_name": "Voltéo"}
    )
    assert created.status_code == 201
    assert created.json()["offer_id"] is None
    assert client.post("/api/applications", json={"title": ""}).status_code == 422


def test_the_contact_is_checked_and_kept(client: TestClient):
    app_id = client.post("/api/applications", json={"title": "Tech Lead"}).json()["id"]
    url = f"/api/applications/{app_id}/contact"

    assert client.put(url, json={"name": "Camille", "email": "pas une adresse"}).status_code == 422
    saved = client.put(url, json={"name": " Camille Roux ", "email": "camille@voltéo.example"})

    assert saved.json()["contact"] == {
        "name": "Camille Roux",
        "email": "camille@voltéo.example",
        "phone": "",
    }


def test_a_deleted_application_is_hidden_and_frees_its_offer(client: TestClient, offer_id: int):
    first = client.post(f"/api/offers/{offer_id}/application").json()["id"]
    assert client.delete(f"/api/applications/{first}").status_code == 204

    assert client.get(f"/api/applications/{first}").status_code == 404
    assert client.get("/api/applications").json() == []
    second = client.post(f"/api/offers/{offer_id}/application").json()["id"]
    assert second != first


def test_unknown_applications_are_not_found(client: TestClient):
    assert client.get("/api/applications/999").status_code == 404
    event = {"type": "note", "occurred_at": "2026-11-07"}
    assert client.post("/api/applications/999/events", json=event).status_code == 404
    assert client.post("/api/offers/999/application").status_code == 404

"""A CV adapted to an offer, through the API: proposed, checked, settled by the user."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from jobingo.db import Conn
from jobingo.domain.offers import ExtractedOffer
from jobingo.llm.client import LLMUnavailable, LLMValidationError, Usage
from jobingo.llm.fake import FakeLLMClient
from jobingo.llm.tasks.extract_offer import ExtractOfferOutput
from jobingo.render.pdf import engine_available
from jobingo.render.verify import compact, extract_pdf_text

needs_engine = pytest.mark.skipif(not engine_available(), reason="WeasyPrint needs Pango")

FIXTURE = (Path(__file__).parent / "fixtures" / "cv.fr.md").read_text(encoding="utf-8")
OFFER = {
    "title": "Ingénieur data plateforme",
    "company": "Plume Énergie",
    "description": "Plateforme de données en Python et Airflow, entrepôt PostgreSQL.",
}


class _Wire(BaseModel):
    resume: str = ""
    experiences: list[str] = []
    bullets: list[str] = []
    competences: list[str] = []
    rewrites: list[dict[str, str]] = []
    discarded: list[dict[str, str]] = []


# On short ids: E1 is nordlys, E3.1 colibri-01, C1 Python, C3 Airflow, C7 Java.
PROPOSAL = _Wire(
    experiences=["E1"],
    bullets=["E1.1", "E1.2"],
    competences=["C3", "C1"],
    rewrites=[
        {"id": "E1.1", "text": "Migration de 120 tâches ETL vers Airflow"},
        {"id": "E1.2", "text": "Réduction de 60 % du coût de l'entrepôt"},
    ],
    discarded=[{"id": "E3.1", "reason": "Java, sans lien avec l'offre"}],
)


@pytest.fixture
def fake(client: TestClient) -> FakeLLMClient:
    fake = FakeLLMClient(model="claude-sonnet-5-5")
    client.app.state.llm_client = fake  # type: ignore[attr-defined]
    return fake


def _save_cv(client: TestClient, text: str = FIXTURE) -> None:
    current = client.get("/api/cv/fr").json()
    response = client.put(
        "/api/cv/fr",
        json={"draft": {"mode": "text", "text": text}, "expected_sha256": current["sha256"]},
    )
    assert response.status_code == 200, response.text


def _application(client: TestClient, fake: FakeLLMClient) -> int:
    """An application made from a stored offer, the way a CV gets adapted."""
    extracted = ExtractedOffer(
        title=OFFER["title"], company_name=OFFER["company"], description_md=OFFER["description"]
    )
    fake.queue("extract_offer", ExtractOfferOutput(offers=[extracted]))
    [offer] = client.post("/api/offers/intake", json={"text": "Une offre."}).json()["offers"]
    app_id: int = client.post(f"/api/offers/{offer['id']}/application").json()["id"]
    return app_id


def _adapt(client: TestClient, app_id: int) -> Any:
    return client.post(f"/api/applications/{app_id}/cv-drafts")


def _create(client: TestClient, fake: FakeLLMClient, answer: Any = PROPOSAL) -> dict[str, Any]:
    _save_cv(client)
    app_id = _application(client, fake)
    fake.queue("select_cv_content", answer)
    response = _adapt(client, app_id)
    assert response.status_code == 201, response.text
    return response.json()


def _by_id(draft: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for experience in draft["experiences"]:
        items[experience["id"]] = experience
        for bullet in experience["bullets"]:
            items[bullet["id"]] = bullet
    for section in ("formation", "competences", "loisirs"):
        for item in draft[section]:
            items[item["id"]] = item
    if draft["resume"]:
        items[draft["resume"]["id"]] = draft["resume"]
    return items


def test_a_draft_shows_the_whole_cv_with_the_proposal_and_its_trail(
    client: TestClient, fake: FakeLLMClient
):
    draft = _create(client, fake)
    items = _by_id(draft)

    assert draft["offer"] == OFFER
    assert draft["llm_call_id"] is not None
    accepted = items["nordlys-01"]
    assert accepted["kept"] and accepted["proposed"]
    assert accepted["text"] == "Migration de 120 tâches ETL vers Airflow"
    assert accepted["original"] == "Migration de 120 tâches ETL de cron vers Airflow"
    refused = items["nordlys-02"]
    assert refused["kept"] and refused["text"] == refused["original"]
    assert refused["proposed_rewrite"] == "Réduction de 60 % du coût de l'entrepôt"
    assert refused["rejected_reason"] == "chiffre absent de la source : 60%"
    left_out = items["colibri-01"]
    assert not left_out["kept"] and not left_out["proposed"]
    assert left_out["discard_reason"] == "Java, sans lien avec l'offre"
    # The summary stays, rewritten or not.
    assert items["resume-01"]["kept"]

    assert draft["application_id"] is not None
    [summary] = client.get(f"/api/applications/{draft['application_id']}/cv-drafts").json()
    assert summary["offer_title"] == OFFER["title"]
    assert summary["llm_call_id"] == draft["llm_call_id"]


def test_the_user_settles_what_goes_on_the_page(client: TestClient, fake: FakeLLMClient):
    draft = _create(client, fake)
    choices = {
        "kept_ids": ["resume-01", "nordlys", "nordlys-02", "colibri", "colibri-01", "unknown"],
        "texts": {
            # Adopting the rewrite code refused is the user's call.
            "nordlys-02": "Réduction de 60 % du coût de l'entrepôt",
            "colibri-01": "  ",
            "unknown": "ignored",
        },
        "options": draft["options"],
    }

    saved = client.put(f"/api/cv/drafts/{draft['id']}/choices", json=choices).json()
    items = _by_id(saved)

    assert items["nordlys-02"]["text"] == "Réduction de 60 % du coût de l'entrepôt"
    assert items["colibri-01"]["kept"]
    assert items["colibri-01"]["text"] == items["colibri-01"]["original"]
    assert not items["nordlys-01"]["kept"]
    # The trail does not move: it is what the model proposed.
    assert items["nordlys-01"]["proposed"]
    reloaded = client.get(f"/api/cv/drafts/{draft['id']}").json()
    assert reloaded == saved


def test_the_source_cv_never_changes(client: TestClient, fake: FakeLLMClient):
    _save_cv(client)
    before = client.get("/api/cv/fr").json()
    draft = _create(client, fake)
    client.put(
        f"/api/cv/drafts/{draft['id']}/choices",
        json={
            "kept_ids": ["nordlys"],
            "texts": {"nordlys": "Autre titre"},
            "options": draft["options"],
        },
    )
    after = client.get("/api/cv/fr").json()
    assert (after["sha256"], after["version"]) == (before["sha256"], before["version"])


@needs_engine
def test_the_pdf_is_the_draft_with_its_texts(client: TestClient, fake: FakeLLMClient):
    draft = _create(client, fake)
    response = client.get(f"/api/cv/drafts/{draft['id']}/pdf")

    assert response.status_code == 200
    assert response.headers["x-page-count"] == "1"
    text = compact(extract_pdf_text(response.content))
    assert compact("Migration de 120 tâches ETL vers Airflow") in text
    assert compact("Maintenance d'applications Java") not in text


def test_without_a_key_nothing_is_called(client: TestClient, fake: FakeLLMClient):
    _save_cv(client)
    app_id = _application(client, fake)
    client.app.state.llm_client = None  # type: ignore[attr-defined]
    response = _adapt(client, app_id)
    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["message"]
    assert client.get(f"/api/applications/{app_id}/cv-drafts").json() == []


@pytest.mark.parametrize(
    ("failure", "status"),
    [
        (LLMUnavailable("down", model="claude-sonnet-5-5", usage=Usage(), request={}), 503),
        (LLMValidationError("bad", model="claude-sonnet-5-5", usage=Usage(), request={}), 502),
    ],
)
def test_a_failed_call_stores_no_draft_and_says_try_again(
    client: TestClient, fake: FakeLLMClient, conn: Conn, failure: Exception, status: int
):
    _save_cv(client)
    app_id = _application(client, fake)
    fake.queue("select_cv_content", failure)  # type: ignore[arg-type]
    response = _adapt(client, app_id)
    assert response.status_code == status
    assert "Réessayez" in response.json()["message"]
    assert client.get(f"/api/applications/{app_id}/cv-drafts").json() == []
    row = conn.execute(
        "SELECT count(*) AS n FROM llm_calls WHERE task = 'select_cv_content'"
    ).fetchone()
    assert row is not None and row["n"] == 1  # journalled all the same


def test_an_empty_cv_is_refused_before_any_call(client: TestClient, fake: FakeLLMClient):
    app_id = _application(client, fake)
    response = _adapt(client, app_id)
    assert response.status_code == 400
    assert "select_cv_content" not in [task for task, _ in fake.prompts]


def test_a_spontaneous_application_adapts_to_what_is_known(client: TestClient, fake: FakeLLMClient):
    _save_cv(client)
    app_id = client.post(
        "/api/applications", json={"title": "Data engineer", "company_name": "Voltéo"}
    ).json()["id"]
    client.put(f"/api/applications/{app_id}/company-notes", json={"notes": "Plateforme Airflow."})
    fake.queue("select_cv_content", PROPOSAL)

    draft = _adapt(client, app_id).json()

    assert (draft["offer_id"], draft["application_id"]) == (None, app_id)
    assert draft["offer"]["title"] == "Data engineer"
    assert "Candidature spontanée" in draft["offer"]["description"]
    assert "Plateforme Airflow." in draft["offer"]["description"]
    _, prompt = fake.prompts[-1]
    assert "Plateforme Airflow." in prompt.user
    assert _adapt(client, 999999).status_code == 404


def test_another_accounts_draft_is_not_found(client: TestClient, fake: FakeLLMClient, conn: Conn):
    draft = _create(client, fake)
    other = conn.execute(
        "INSERT INTO users (username) VALUES ('someone-else') RETURNING id"
    ).fetchone()
    assert other is not None
    conn.execute("UPDATE cv_drafts SET user_id = %s", (other["id"],))
    assert client.get(f"/api/cv/drafts/{draft['id']}").status_code == 404
    assert client.get(f"/api/cv/drafts/{draft['id']}/pdf").status_code == 404
    assert client.get(f"/api/applications/{draft['application_id']}/cv-drafts").json() == []

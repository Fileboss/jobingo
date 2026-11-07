"""Scoring: filters in code, four ratings from the model, every score computed by code."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from jobingo.domain.objectives import Weights
from jobingo.domain.offers import ExtractedOffer
from jobingo.domain.scoring import Criteria, fit_score, global_score
from jobingo.llm.client import LLMUnavailable, Usage
from jobingo.llm.fake import FakeLLMClient
from jobingo.llm.tasks.extract_offer import ExtractOfferOutput
from jobingo.llm.tasks.score_offer import ScoreOfferOutput

FIXTURE = (Path(__file__).parent / "fixtures" / "cv.fr.md").read_text(encoding="utf-8")
DATA = ExtractedOffer(
    title="Data engineer",
    company_name="Plume Énergie",
    location="Lyon",
    contract="CDI",
    salary_min=55000,
    salary_max=62000,
    description_md="Pipelines Airflow.",
)
JAVA = ExtractedOffer(title="Développeur Java", company_name="Banque Rhône", contract="CDD")
RATINGS = ScoreOfferOutput(
    mission=8, stack=9, salary=6, culture=7, strengths=["Airflow"], summary="Bon accord."
)


def test_scores_are_weighted_averages_on_100():
    criteria = Criteria(mission=8, stack=9, salary=6, culture=7)
    assert global_score(criteria, Weights()) == 75
    assert global_score(criteria, Weights(mission=2, stack=2, salary=1, culture=1)) == 78
    assert fit_score(criteria, Weights()) == 80
    assert global_score(criteria, Weights(mission=0, stack=0, salary=0, culture=0)) == 0


@pytest.fixture
def fake(client: TestClient) -> FakeLLMClient:
    fake = FakeLLMClient()
    client.app.state.llm_client = fake  # type: ignore[attr-defined]
    current = client.get("/api/cv/fr").json()
    client.put(
        "/api/cv/fr",
        json={"draft": {"mode": "text", "text": FIXTURE}, "expected_sha256": current["sha256"]},
    )
    return fake


def _objectives(client: TestClient, **body: Any) -> None:
    response = client.put("/api/objectives", json=body)
    assert response.status_code == 200, response.text


def _intake(client: TestClient, fake: FakeLLMClient, *offers: ExtractedOffer) -> Any:
    fake.queue("extract_offer", ExtractOfferOutput(offers=list(offers)))
    response = client.post("/api/offers/intake", json={"text": "Des offres."})
    assert response.status_code == 201, response.text
    return response.json()


def test_intake_scores_what_passes_and_filters_the_rest_without_a_call(
    client: TestClient, fake: FakeLLMClient
):
    _objectives(
        client,
        hard_filters={"contracts": ["CDI"]},
        weights={"mission": 2, "stack": 2, "salary": 1, "culture": 1},
        preferences="Plateformes de données.",
    )
    fake.queue("score_offer", RATINGS)

    result = _intake(client, fake, DATA, JAVA)

    assert result["unscored_ids"] == [] and result["scoring_error"] is None
    assert [task for task, _ in fake.prompts] == ["extract_offer", "score_offer"]
    _, prompt = fake.prompts[1]
    assert "Plateformes de données." in prompt.user
    assert "airflow" in prompt.user  # the CV's tags
    listed = {offer["title"]: offer for offer in client.get("/api/offers").json()}
    data, java = listed["Data engineer"], listed["Développeur Java"]
    assert data["state"] == "scored"
    score = data["current_score"]
    assert (score["score"], score["fit_score"], score["salary_score"]) == (78, 82, 60)
    assert score["weights"] == {"mission": 2, "stack": 2, "salary": 1, "culture": 1}
    assert score["llm_call_id"] is not None and not score["stale"]
    assert java["state"] == "filtered"
    assert java["current_score"]["eliminated_by"] == ["contrat non retenu : CDD"]
    assert java["current_score"]["llm_call_id"] is None


def test_an_offer_without_salary_has_no_salary_score(client: TestClient, fake: FakeLLMClient):
    fake.queue("score_offer", RATINGS)
    _intake(client, fake, JAVA)
    [offer] = client.get("/api/offers").json()
    assert offer["current_score"]["salary_score"] is None
    assert offer["current_score"]["score"] == 75  # the rating still counts in the score


def test_a_failed_scoring_keeps_the_offer_and_says_so(client: TestClient, fake: FakeLLMClient):
    down = LLMUnavailable("down", model="claude-haiku-5-5", usage=Usage(), request={})
    fake.queue("score_offer", down)

    result = _intake(client, fake, DATA, JAVA)

    assert len(result["offers"]) == 2
    assert len(result["unscored_ids"]) == 2  # it stops at the first failure
    assert result["scoring_error"] == "le modèle n'a pas pu noter l'offre"
    assert all(o["state"] == "new" for o in client.get("/api/offers").json())


def test_the_users_decision_survives_scoring(client: TestClient, fake: FakeLLMClient):
    fake.queue("score_offer", RATINGS)
    [offer] = _intake(client, fake, DATA)["offers"]
    decided = client.put(
        f"/api/offers/{offer['id']}/decision", json={"decision": "dismissed"}
    ).json()
    assert decided["decision"] == "dismissed"

    fake.queue("score_offer", RATINGS)
    rescored = client.post(f"/api/offers/{offer['id']}/score").json()

    assert rescored["decision"] == "dismissed"
    assert rescored["state"] == "scored"
    taken_back = client.put(f"/api/offers/{offer['id']}/decision", json={"decision": None})
    assert taken_back.json()["decision"] is None


def test_changed_objectives_make_scores_stale_and_rescoring_updates_them(
    client: TestClient, fake: FakeLLMClient
):
    fake.queue("score_offer", RATINGS)
    _intake(client, fake, DATA)
    assert client.get("/api/offers/stale").json() == {"count": 0}

    _objectives(client, weights={"mission": 3, "stack": 1, "salary": 1, "culture": 1})
    [offer] = client.get("/api/offers").json()
    assert offer["current_score"]["stale"]
    assert client.get("/api/offers/stale").json() == {"count": 1}

    fake.queue("score_offer", RATINGS)
    run = client.post("/api/offers/rescore").json()

    assert run == {"scored_ids": [offer["id"]], "unscored_ids": [], "error": None}
    [rescored] = client.get("/api/offers").json()
    assert not rescored["current_score"]["stale"]
    assert rescored["current_score"]["score"] == 77


def test_scoring_needs_a_key_and_an_existing_offer(client: TestClient, fake: FakeLLMClient):
    assert client.post("/api/offers/999/score").status_code == 404
    client.app.state.llm_client = None  # type: ignore[attr-defined]
    assert client.post("/api/offers/rescore").status_code == 503

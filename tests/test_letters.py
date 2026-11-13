"""Cover letters: the model writes the slots, code checks each one, the user decides."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from jobingo.domain.letter import LetterProposal, LetterSources, SlotSpec, validate_slot
from jobingo.domain.offers import ExtractedOffer
from jobingo.domain.style import StyleGuide
from jobingo.llm.fake import FakeLLMClient
from jobingo.llm.tasks.extract_offer import ExtractOfferOutput
from jobingo.render.letter import LETTER_DIR, french_date, load_letter_manifest
from jobingo.render.pdf import engine_available
from jobingo.render.verify import compact, extract_pdf_text

needs_engine = pytest.mark.skipif(not engine_available(), reason="WeasyPrint needs Pango")
FIXTURE = (Path(__file__).parent / "fixtures" / "cv.fr.md").read_text(encoding="utf-8")
SOURCES = LetterSources(
    realisations="Migration de 120 tâches ETL vers Airflow",
    offre="Data engineer\nPlume Énergie\nPlateforme de données.",
    notes_entreprise="Produit utilisé par 300 collectivités.",
)
ONLY_CV = SlotSpec(name="adequation", max_words=20, sources=["realisations"])


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("J'ai migré 120 tâches vers Airflow.", None),
        ("J'ai migré 150 tâches vers Airflow.", "chiffre absent des sources : 150"),
        # The figure is in the notes, but this slot may only use the CV.
        ("Vos 300 collectivités m'intéressent.", "chiffre absent des sources : 300"),
        (" ".join(["mot"] * 21), "21 mots, le modèle en autorise 20"),
        ("Fort de mon expérience, j'ai migré des tâches.", "tournure interdite"),
    ],
)
def test_a_slot_keeps_to_its_sources_and_limits(text: str, reason: str | None):
    style = StyleGuide(forbidden=["fort de mon expérience"])
    refused = validate_slot(text, ONLY_CV, SOURCES, style)
    if reason is None:
        assert refused is None
    else:
        assert refused is not None and refused.startswith(reason)


def test_a_slot_without_declared_sources_may_use_all():
    open_slot = SlotSpec(name="accroche", max_words=60)
    assert validate_slot("Vos 300 collectivités.", open_slot, SOURCES, StyleGuide()) is None


def test_the_shipped_template_uses_exactly_its_declared_slots():
    """A declared slot missing from the body would drop text the user reviewed."""
    body = (LETTER_DIR / "template.html").read_text(encoding="utf-8")
    used = set(__import__("re").findall(r"slots\.([a-z_]+)", body))
    assert used == {spec.name for spec in load_letter_manifest().slots}


def test_dates_are_written_in_french():
    from datetime import date

    assert french_date(date(2026, 11, 1)) == "1er novembre 2026"
    assert french_date(date(2026, 8, 15)) == "15 août 2026"


def test_paragraphs_keep_a_figure_with_its_unit():
    from jobingo.render.letter import paragraphs

    assert paragraphs("De 20 à 85 %,\nsur 60 k€.\n\nSuite.") == [
        "De 20 à 85\u00a0%, sur 60\u00a0k€.",
        "Suite.",
    ]


def test_the_wire_pairs_fold_into_slots():
    proposal = LetterProposal.model_validate(
        {"slots": [{"name": "accroche", "text": "Bonjour"}], "cited_ids": ["nordlys"]}
    )
    assert proposal.slots == {"accroche": "Bonjour"}


# --- Through the API -------------------------------------------------------------------------


class _Wire(BaseModel):
    slots: list[dict[str, str]]
    cited_ids: list[str] = []


GOOD = _Wire(
    slots=[
        {
            "name": "accroche",
            "text": "Votre poste de data engineer chez Plume Énergie m'intéresse.",
        },
        {
            "name": "adequation",
            "text": "J'ai migré 120 tâches ETL de cron vers Airflow, comme chez Stratus.",
        },
        {"name": "motivation", "text": "Votre plateforme sert 400 collectivités."},
    ],
    cited_ids=["nordlys-01", "inconnu"],
)


@pytest.fixture
def application(client: TestClient) -> int:
    fake = FakeLLMClient()
    client.app.state.llm_client = fake  # type: ignore[attr-defined]
    current = client.get("/api/cv/fr").json()
    client.put(
        "/api/cv/fr",
        json={"draft": {"mode": "text", "text": FIXTURE}, "expected_sha256": current["sha256"]},
    )
    offer = ExtractedOffer(
        title="Data engineer", company_name="Plume Énergie", description_md="Plateforme."
    )
    fake.queue("extract_offer", ExtractOfferOutput(offers=[offer]))
    [stored] = client.post("/api/offers/intake", json={"text": "x"}).json()["offers"]
    app_id: int = client.post(f"/api/offers/{stored['id']}/application").json()["id"]
    notes = {"notes": "Produit utilisé par 300 collectivités."}
    assert client.put(f"/api/applications/{app_id}/company-notes", json=notes).status_code == 204
    return app_id


def _fake(client: TestClient) -> FakeLLMClient:
    return client.app.state.llm_client  # type: ignore[attr-defined, no-any-return]


def _propose(client: TestClient, app_id: int, answer: Any = GOOD) -> Any:
    _fake(client).queue("draft_letter", answer)
    response = client.post(f"/api/applications/{app_id}/letters")
    assert response.status_code == 201, response.text
    return response.json()


def test_a_letter_keeps_accepted_slots_and_empties_refused_ones(
    client: TestClient, application: int
):
    letter = _propose(client, application)
    slots = {slot["name"]: slot for slot in letter["slots"]}

    assert slots["accroche"]["text"].startswith("Votre poste")
    assert slots["adequation"]["text"].startswith("J'ai migré 120")
    refused = slots["motivation"]
    assert refused["text"] == ""
    assert refused["proposed"] == "Votre plateforme sert 400 collectivités."
    assert refused["rejected_reason"] == "chiffre absent des sources : 400"
    assert slots["adequation"]["unsourced_names"] == ["Stratus"]  # not in the CV
    assert letter["cited_ids"] == ["nordlys-01"]
    assert letter["warnings"] == ["réalisation citée inconnue, ignorée : « inconnu »"]
    assert letter["problems"] == ["« motivation » est vide"]
    assert letter["recipient"] == "Plume Énergie"
    _, prompt = _fake(client).prompts[-1]
    assert prompt.system is not None and "Produit utilisé par 300 collectivités." in prompt.system
    [listed] = client.get(f"/api/applications/{application}/letters").json()
    assert listed["id"] == letter["id"]


def test_the_user_writes_what_was_refused(client: TestClient, application: int):
    letter = _propose(client, application)
    texts = {slot["name"]: slot["text"] for slot in letter["slots"]}
    texts["motivation"] = "Votre plateforme sert 400 collectivités, je l'ai vérifié."
    texts["inconnu"] = "ignoré"

    saved = client.put(
        f"/api/letters/{letter['id']}/texts", json={"texts": texts, "recipient": "Camille Roux"}
    ).json()

    assert saved["problems"] == []
    assert saved["recipient"] == "Camille Roux"
    motivation = next(slot for slot in saved["slots"] if slot["name"] == "motivation")
    assert motivation["rejected_reason"]  # the trail stays
    too_long = {**texts, "accroche": " ".join(["mot"] * 61)}
    blocked = client.put(f"/api/letters/{letter['id']}/texts", json={"texts": too_long}).json()
    assert blocked["problems"] == ["« accroche » fait 61 mots, 60 au plus"]


@needs_engine
def test_the_pdf_puts_the_identity_back_at_render_time(client: TestClient, application: int):
    client.put(
        "/api/identity",
        json={
            "name": "Alex Moreau",
            "email": "alex@example.org",
            "phone": "",
            "address": "Lyon",
            "linkedin": "",
            "github": "",
        },
    )
    letter = _propose(client, application)

    response = client.get(f"/api/letters/{letter['id']}/pdf")

    assert response.status_code == 200
    assert response.headers["x-page-count"] == "1"
    assert 'filename="lettre-alex-moreau.pdf"' in response.headers["content-disposition"]
    text = compact(extract_pdf_text(response.content))
    assert compact("Alex Moreau") in text
    assert compact("Objet : candidature — Data engineer") in text
    assert compact("J'ai migré 120 tâches ETL") in text
    # The identity went into the PDF, never into the prompt.
    _, prompt = _fake(client).prompts[-1]
    assert "Alex" not in (prompt.system or "") + prompt.user


def test_no_letter_without_a_key_or_an_application(client: TestClient, application: int):
    assert client.post("/api/applications/999/letters").status_code == 404
    client.app.state.llm_client = None  # type: ignore[attr-defined]
    assert client.post(f"/api/applications/{application}/letters").status_code == 503
    assert client.get("/api/letters/999").status_code == 404


def test_a_letter_is_deleted_for_good(client: TestClient, application: int):
    letter = _propose(client, application)

    assert client.delete(f"/api/letters/{letter['id']}").status_code == 204

    assert client.get(f"/api/letters/{letter['id']}").status_code == 404
    assert client.get(f"/api/applications/{application}/letters").json() == []
    assert client.delete(f"/api/letters/{letter['id']}").status_code == 404

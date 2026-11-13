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
    sert_l_offre: list[str] = []
    complement: list[str] = []
    competences: list[str] = []
    rewrites: list[dict[str, str]] = []
    discarded: list[dict[str, str]] = []


# On short ids: E1 is nordlys, E3.1 colibri-01, C1 Python, C3 Airflow, C7 Java.
PROPOSAL = _Wire(
    sert_l_offre=["E1", "E1.1", "E1.2"],
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


def _long_cv() -> str:
    """Four experiences of four long bullets: everything kept runs over the page."""
    bullet = (
        "Conduite d'un chantier de fiabilisation de la plateforme de données, de "
        "l'analyse des incidents à la refonte des traitements, avec un suivi hebdomadaire "
        "des indicateurs de qualité partagé avec les équipes produit et métier, puis "
        "la reprise de la documentation d'exploitation et la formation des équipes "
        "d'astreinte aux nouveaux outils de supervision et de reprise sur incident"
    )
    lines = ["---", "lang: fr", "---", "", "## Expériences", ""]
    for e in range(1, 5):
        dates = f"01/20{10 + e} – 12/20{11 + e}"
        lines.append(f"### Société {e} — Ingénieur data — {dates} <!-- id=x{e} -->")
        lines.append("")
        lines += [f"- {bullet} {e}.{b} <!-- id=x{e}-{b} -->" for b in range(1, 5)]
        lines.append("")
    return "\n".join(lines)


# Everything, in CV order: four experiences of four bullets run over the page.
EVERYTHING = _Wire(
    sert_l_offre=[i for e in range(1, 5) for i in (f"E{e}", *(f"E{e}.{b}" for b in range(1, 5)))],
)
SHORT = "Fiabilisation de la plateforme de données"
MEAGRE = _Wire(
    sert_l_offre=["E1", "E1.1", "E1.2", "E2", "E2.1"], rewrites=[{"id": "E1.1", "text": SHORT}]
)


def _create_long(client: TestClient, fake: FakeLLMClient, answer: BaseModel) -> dict[str, Any]:
    _save_cv(client, _long_cv())
    app_id = _application(client, fake)
    fake.queue("select_cv_content", answer)
    response = _adapt(client, app_id)
    assert response.status_code == 201, response.text
    return response.json()


@needs_engine
def test_the_ranking_is_taken_in_order_as_far_as_the_page_holds(
    client: TestClient, fake: FakeLLMClient
):
    draft = _create_long(client, fake, EVERYTHING)

    [prompt] = [p.user for name, p in fake.prompts if name == "select_cv_content"]
    assert "Expériences : sans limite" in prompt  # one call
    items = _by_id(draft)
    kept = [item_id for item_id, item in items.items() if item["kept"]]
    # The head of the ranking, in its order: the first two experiences whole.
    assert kept[:10] == [f"x{e}{b}" for e in (1, 2) for b in ("", "-1", "-2", "-3", "-4")]
    left = [item for item in items.values() if not item["kept"]]
    assert left and all(item["discarded_by_code"] for item in left)
    assert all(item["discard_reason"].startswith("faute de place") for item in left)
    assert "x4-4" in [item["id"] for item in left]
    assert draft["warnings"] == []  # 80 % to 100 % full
    pdf = client.get(f"/api/cv/drafts/{draft['id']}/pdf")
    assert pdf.headers["x-page-count"] == "1"


@needs_engine
def test_a_ranking_too_short_for_the_page_says_so(client: TestClient, fake: FakeLLMClient):
    draft = _create_long(client, fake, MEAGRE)

    kept = [item_id for item_id, item in _by_id(draft).items() if item["kept"]]
    assert kept == ["x1", "x1-1", "x1-2", "x2", "x2-1"]
    assert _by_id(draft)["x1-1"]["text"] == SHORT
    [warning] = draft["warnings"]
    assert "le modèle n'a classé que 5 éléments" in warning


def test_what_only_completes_the_page_is_said_so(client: TestClient, fake: FakeLLMClient):
    answer = PROPOSAL.model_copy(update={"complement": ["E2", "E2.1"]})
    items = _by_id(_create(client, fake, answer))

    assert items["batiflux"]["kept"] and items["batiflux"]["complement"]
    assert items["batiflux-01"]["complement"]
    assert not items["nordlys"]["complement"]


def _long_skills() -> str:
    """Ten long skill lines: more than the side panel holds."""
    skill = (
        "Données : bases orientées graphe, requêtage natif sans surcouche d'abstraction, "
        "bases relationnelles, chaînes de traitement, analyse et visualisation, "
        "orchestration des traitements, supervision, documentation et formation des "
        "équipes, revue des modèles de données et des performances en production"
    )
    lines = [f"- {skill} {n} <!-- id=sk{n} -->" for n in range(1, 11)]
    return "\n\n## Compétences\n\n" + "\n".join(lines) + "\n"


@needs_engine
def test_a_side_panel_too_long_is_cut_apart_and_the_column_still_fills(
    client: TestClient, fake: FakeLLMClient
):
    """Regression: the panel ran off its page, so every head of the ranking counted as
    running over, and code emptied the main column down to the summary."""
    _save_cv(client, _long_cv() + _long_skills() + "\n## Langues\n\n- Anglais : C1\n")
    app_id = _application(client, fake)
    skills = [f"C{n}" for n in range(1, 11)]
    fake.queue("select_cv_content", EVERYTHING.model_copy(update={"competences": skills}))
    draft = _adapt(client, app_id).json()

    items = _by_id(draft)
    kept = [item_id for item_id, item in items.items() if item["kept"]]
    assert kept[:10] == [f"x{e}{b}" for e in (1, 2) for b in ("", "-1", "-2", "-3", "-4")]
    left_skills = [item for item in draft["competences"] if not item["kept"]]
    assert left_skills and all(item["discarded_by_code"] for item in left_skills)
    assert all("panneau latéral" in item["discard_reason"] for item in left_skills)
    # The least useful go: the model's first skills stay.
    assert draft["competences"][0]["kept"]
    # Languages are never cut for room, and the model was never shown them.
    assert [item["kept"] for item in draft["langues"]] == [True]
    [prompt] = [
        p.user + (p.system or "") for name, p in fake.prompts if name == "select_cv_content"
    ]
    assert "Anglais : C1" not in prompt
    pdf = client.get(f"/api/cv/drafts/{draft['id']}/pdf")
    assert pdf.headers["x-page-count"] == "1"
    assert pdf.headers.get("x-missing-items", "0") == "0"


def test_the_draft_downloads_as_one_self_contained_html_file(
    client: TestClient, fake: FakeLLMClient
):
    draft = _create(client, fake)
    response = client.get(f"/api/cv/drafts/{draft['id']}/html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;") and disposition.endswith('.html"')
    html = response.text
    assert "Migration de 120 tâches ETL vers Airflow" in html  # the draft as it stands
    assert "Maintenance d'applications Java" not in html
    # Nothing fetched: the stylesheet inlined, its fonts as data.
    assert "<style>" in html and "data:font/woff;base64," in html
    assert 'url("fonts/' not in html and "http://" not in html.replace("http://www.w3.org", "")
    assert client.get("/api/cv/drafts/999999/html").status_code == 404


@needs_engine
def test_every_experience_ranked_goes_on_a_page_with_room(client: TestClient, fake: FakeLLMClient):
    """Regression: a template cap of four experiences cut the fifth ranked, a recent
    role, leaving a gap in the career although the page had room."""
    jobs = "\n\n".join(
        f"### Société {n} — Développeur — 01/20{10 + n} – 12/20{10 + n} <!-- id=job{n} -->\n\n"
        f"- Réalisation courte {n} <!-- id=job{n}-1 -->"
        for n in range(1, 7)
    )
    _save_cv(client, f"---\nlang: fr\n---\n\n## Expériences\n\n{jobs}\n")
    app_id = _application(client, fake)
    ranking = [i for n in range(1, 7) for i in (f"E{n}", f"E{n}.1")]
    fake.queue("select_cv_content", _Wire(sert_l_offre=ranking))
    draft = _adapt(client, app_id).json()

    assert all(experience["kept"] for experience in draft["experiences"])
    assert len(draft["experiences"]) == 6


def test_an_adapted_cv_is_deleted_for_good(client: TestClient, fake: FakeLLMClient):
    draft = _create(client, fake)
    app_id = draft["application_id"]

    assert client.delete(f"/api/cv/drafts/{draft['id']}").status_code == 204

    assert client.get(f"/api/cv/drafts/{draft['id']}").status_code == 404
    assert client.get(f"/api/applications/{app_id}/cv-drafts").json() == []
    assert client.delete(f"/api/cv/drafts/{draft['id']}").status_code == 404
    # The model call stays in the journal, with what it cost.
    assert client.get(f"/api/observability/calls/{draft['llm_call_id']}").status_code == 200

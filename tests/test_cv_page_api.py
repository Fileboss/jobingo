"""The identity, the page selection and the PDF, through the API, on real PDFs."""

import base64
import io
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader
from tests.images import jpeg_bytes, png_bytes

from jobingo.config import Settings
from jobingo.db import Conn
from jobingo.render.pdf import engine_available
from jobingo.render.verify import compact, extract_pdf_text
from jobingo.services import cv_page, photo
from jobingo.services.accounts import ensure_account
from jobingo_api.main import create_app

needs_engine = pytest.mark.skipif(not engine_available(), reason="WeasyPrint needs Pango")

FIXTURE = (Path(__file__).parent / "fixtures" / "cv.fr.md").read_text(encoding="utf-8")
HOBBIES = "\n## Loisirs\n\n- Escalade\n- Photographie\n"
ALEX = {
    "name": "Alex Moreau",
    "email": "alex.moreau@example.org",
    "phone": "06 00 00 00 00",
    "address": "12 rue des Lilas, 69003 Lyon",
    "linkedin": "linkedin.com/in/alex-moreau",
    "github": "github.com/alex-moreau",
}
# What a client with no photo and a CV with no hobbies sends back.
AS_SHOWN = {"photo": False, "panneau_competences": True, "loisirs": False}


def _save_cv(client: TestClient, text: str = FIXTURE) -> None:
    current = client.get("/api/cv/fr").json()
    response = client.put(
        "/api/cv/fr",
        json={"draft": {"mode": "text", "text": text}, "expected_sha256": current["sha256"]},
    )
    assert response.status_code == 200, response.text


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _upload(client: TestClient, data: bytes) -> Any:
    return client.put("/api/identity/photo", json={"data_base64": _b64(data)})


def _choose(client: TestClient, excluded: list[str], **options: bool) -> Any:
    return client.put(
        "/api/cv/fr/selection",
        json={"excluded_ids": excluded, "options": {**AS_SHOWN, **options}},
    )


# --- identity ---------------------------------------------------------------------


def test_a_new_account_has_an_empty_identity(client: TestClient):
    response = client.get("/api/identity")

    assert response.status_code == 200
    assert response.json() == {
        "name": "",
        "email": "",
        "phone": "",
        "address": "",
        "linkedin": "",
        "github": "",
        "has_photo": False,
    }


def test_a_saved_identity_replaces_the_previous_and_survives_a_restart(
    settings: Settings, conn: Conn
):
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as first:
        assert first.put("/api/identity", json=ALEX).status_code == 200
        replaced = first.put("/api/identity", json={**ALEX, "phone": "  ", "name": "Alex M."})
        assert replaced.json()["phone"] == "" and replaced.json()["name"] == "Alex M."
        assert _upload(first, jpeg_bytes()).json()["has_photo"] is True
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as second:
        loaded = second.get("/api/identity").json()
        assert loaded["name"] == "Alex M." and loaded["has_photo"] is True
        assert second.get("/api/identity/photo").status_code == 200


def test_saving_the_identity_keeps_the_photo(client: TestClient):
    _upload(client, jpeg_bytes())

    assert client.put("/api/identity", json=ALEX).json()["has_photo"] is True


def test_identity_and_photo_responses_are_not_cached(client: TestClient):
    _upload(client, jpeg_bytes())
    for path in ("/api/identity", "/api/identity/photo"):
        assert client.get(path).headers["cache-control"] == "no-store"


# --- photo ------------------------------------------------------------------------


def test_a_photo_can_be_shown_and_removed(client: TestClient):
    assert client.get("/api/identity/photo").status_code == 404
    _upload(client, jpeg_bytes())

    shown = client.get("/api/identity/photo")

    assert shown.headers["content-type"] == "image/jpeg"
    assert shown.content.startswith(b"\xff\xd8")
    assert client.delete("/api/identity/photo").json()["has_photo"] is False
    assert client.get("/api/identity/photo").status_code == 404
    assert client.delete("/api/identity/photo").status_code == 200


def test_a_png_with_transparency_is_flattened_to_jpeg(client: TestClient):
    assert _upload(client, png_bytes()).status_code == 200

    shown = Image.open(io.BytesIO(client.get("/api/identity/photo").content))

    assert shown.format == "JPEG"
    assert shown.getpixel((1, 1)) == (255, 255, 255)


def test_exif_and_comments_are_not_kept_and_the_orientation_is_applied(client: TestClient):
    exif = Image.Exif()
    exif[0x010F] = "Appareil de test"  # Make
    exif[0x0112] = 6  # Orientation: rotated, so width and height swap
    source = io.BytesIO()
    Image.new("RGB", (60, 80), "steelblue").save(
        source, format="JPEG", exif=exif, comment=b"Commentaire de test"
    )

    assert _upload(client, source.getvalue()).status_code == 200

    stored = client.get("/api/identity/photo").content
    image = Image.open(io.BytesIO(stored))
    assert dict(image.getexif()) == {}
    assert b"Appareil de test" not in stored and b"Commentaire de test" not in stored
    assert image.size == (80, 60)


def test_a_large_photo_is_scaled_down(client: TestClient):
    assert _upload(client, jpeg_bytes((1600, 2000))).status_code == 200

    image = Image.open(io.BytesIO(client.get("/api/identity/photo").content))

    assert max(image.size) == photo.MAX_SIDE


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("", "Aucun fichier"),
        ("pas du base64 !", "illisible"),
        (_b64(b"du texte, pas une image"), "illisible"),
        (_b64(b"GIF89a"), "illisible"),
        ("A" * ((photo.MAX_UPLOAD_BYTES + 2) // 3 * 4 + 4), "trop lourde"),
    ],
)
def test_an_unusable_upload_is_refused_in_french(client: TestClient, body: str, expected: str):
    response = client.put("/api/identity/photo", json={"data_base64": body})

    assert response.status_code == 400
    assert expected in response.json()["message"]
    assert client.get("/api/identity").json()["has_photo"] is False


def test_a_format_other_than_jpeg_or_png_is_refused(client: TestClient):
    out = io.BytesIO()
    Image.new("RGB", (10, 10)).save(out, format="GIF")

    response = _upload(client, out.getvalue())

    assert response.status_code == 400
    assert "JPEG et PNG" in response.json()["message"]


def test_a_picture_over_the_pixel_limit_is_refused(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(photo, "MAX_SOURCE_PIXELS", 100)

    response = _upload(client, jpeg_bytes())

    assert response.status_code == 400
    assert "mégapixels" in response.json()["message"]


def test_a_refused_photo_leaves_the_previous_one(client: TestClient):
    _upload(client, jpeg_bytes())

    assert _upload(client, b"rien").status_code == 400

    assert client.get("/api/identity").json()["has_photo"] is True


# --- selection --------------------------------------------------------------------


def test_everything_is_selected_by_default(client: TestClient):
    _save_cv(client, FIXTURE + HOBBIES)

    page = client.get("/api/cv/fr/selection").json()

    assert page["excluded_ids"] == []
    assert page["max_pages"] == 1
    assert page["resume"]["text"].startswith("Ingénieur backend")
    assert page["resume"]["selected"] is True
    assert [e["id"] for e in page["experiences"]] == ["nordlys", "batiflux", "colibri"]
    items = [
        *page["experiences"],
        *[b for e in page["experiences"] for b in e["bullets"]],
        *page["formation"],
        *page["competences"],
        *page["loisirs"],
    ]
    assert all(item["selected"] for item in items)
    assert page["options"] == {**AS_SHOWN, "loisirs": True}


def test_an_experience_comes_with_its_dates_apart(client: TestClient):
    _save_cv(
        client, "## Expériences\n\n### Libre sans séparateur 2020\n\n### A — B — 2020 – 2021\n"
    )

    free, structured = client.get("/api/cv/fr/selection").json()["experiences"]

    assert (free["text"], free["dates"]) == ("Libre sans séparateur 2020", "")
    assert (structured["text"], structured["dates"]) == ("A — B", "2020 – 2021")


def test_a_formation_heading_is_marked_and_can_be_left_out(client: TestClient):
    _save_cv(client, "## Formation\n\n### Diplômes\n\n- Ingénieur, 2016\n")

    heading, line = client.get("/api/cv/fr/selection").json()["formation"]

    assert (heading["heading"], line["heading"]) == (True, False)
    page = _choose(client, [heading["id"]]).json()
    assert [item["selected"] for item in page["formation"]] == [False, True]


def test_a_cv_never_saved_has_an_empty_page(client: TestClient):
    page = client.get("/api/cv/fr/selection").json()

    assert page["resume"] is None and page["experiences"] == []
    assert page["options"]["loisirs"] is False


def test_the_choice_survives_a_reload_and_can_be_undone(client: TestClient):
    _save_cv(client)

    saved = _choose(client, ["nordlys-02", "skill-java"], panneau_competences=False)

    assert saved.status_code == 200
    page = client.get("/api/cv/fr/selection").json()
    assert page["excluded_ids"] == ["nordlys-02", "skill-java"]
    assert page["options"]["panneau_competences"] is False
    bullets = {b["id"]: b["selected"] for b in page["experiences"][0]["bullets"]}
    assert bullets["nordlys-02"] is False and bullets["nordlys-01"] is True

    assert _choose(client, []).json()["excluded_ids"] == []


def test_a_bullet_keeps_its_own_choice_when_its_experience_is_unticked(client: TestClient):
    _save_cv(client)

    page = _choose(client, ["nordlys"]).json()

    assert page["experiences"][0]["selected"] is False
    assert all(bullet["selected"] for bullet in page["experiences"][0]["bullets"])


def test_a_removed_id_is_ignored_and_a_new_item_is_selected(client: TestClient):
    _save_cv(client)
    _choose(client, ["skill-java", "skill-docker"])

    edited = FIXTURE.replace("- Java <!-- id=skill-java -->\n", "- Rust <!-- id=skill-rust -->\n")
    _save_cv(client, edited)

    page = client.get("/api/cv/fr/selection").json()
    assert page["excluded_ids"] == ["skill-docker"]
    assert {c["id"]: c["selected"] for c in page["competences"]}["skill-rust"] is True


def test_an_unknown_id_is_not_stored(client: TestClient):
    _save_cv(client)

    assert _choose(client, ["n-existe-pas", "skill-java"]).json()["excluded_ids"] == ["skill-java"]


def test_the_selection_of_one_user_does_not_reach_another(conn: Conn, client: TestClient):
    _save_cv(client)
    _choose(client, ["skill-java"])
    other = ensure_account(conn, "autre-compte")

    assert cv_page.load_page(conn, other.id, "fr").excluded_ids == []


# --- options ----------------------------------------------------------------------


def test_the_photo_option_needs_a_photo(client: TestClient):
    _save_cv(client)

    page = client.get("/api/cv/fr/selection").json()
    assert page["options"]["photo"] is False
    assert "photo" in page["option_blockers"]["photo"]

    refused = _choose(client, [], photo=True)
    assert refused.status_code == 400
    assert "photo" in refused.json()["message"]

    _upload(client, jpeg_bytes())
    assert client.get("/api/cv/fr/selection").json()["option_blockers"]["photo"] is None
    assert _choose(client, [], photo=True).json()["options"]["photo"] is True


def test_the_hobbies_option_needs_hobbies(client: TestClient):
    _save_cv(client)

    page = client.get("/api/cv/fr/selection").json()
    assert page["options"]["loisirs"] is False
    assert "Loisirs" in page["option_blockers"]["loisirs"]
    assert _choose(client, [], loisirs=True).status_code == 400

    _save_cv(client, FIXTURE + HOBBIES)
    page = client.get("/api/cv/fr/selection").json()
    assert page["options"]["loisirs"] is True and page["option_blockers"]["loisirs"] is None


def test_a_choice_made_while_an_option_is_blocked_does_not_turn_it_off_for_later(
    client: TestClient,
):
    _save_cv(client)
    _choose(client, ["skill-java"])  # sends loisirs off, as the screen shows it

    _save_cv(client, FIXTURE + HOBBIES)

    assert client.get("/api/cv/fr/selection").json()["options"]["loisirs"] is True


def test_removing_the_photo_turns_its_option_off_without_an_error(client: TestClient):
    _save_cv(client)
    _upload(client, jpeg_bytes())
    _choose(client, [], photo=True)

    client.delete("/api/identity/photo")

    assert client.get("/api/cv/fr/selection").json()["options"]["photo"] is False


# --- PDF --------------------------------------------------------------------------


@needs_engine
def test_the_pdf_carries_identity_selection_and_headers(client: TestClient):
    _save_cv(client)
    client.put("/api/identity", json=ALEX)
    _choose(client, ["nordlys-03"])

    response = client.get("/api/cv/fr/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-page-count"] == "1"
    assert response.headers["content-disposition"] == 'inline; filename="cv-alex-moreau.pdf"'
    text = compact(extract_pdf_text(response.content))
    assert compact("Alex Moreau") in text and "alex.moreau@example.org" in text
    assert compact("Migration de 120 tâches") in text
    assert compact("API de facturation") not in text


@needs_engine
def test_without_an_identity_the_pdf_still_renders_with_a_neutral_name(client: TestClient):
    _save_cv(client)
    _choose(client, [])

    response = client.get("/api/cv/fr/pdf")

    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'inline; filename="cv.pdf"'
    assert "Nordlys" in extract_pdf_text(response.content)


@needs_engine
def test_a_name_with_accents_gives_an_ascii_filename(client: TestClient):
    client.put("/api/identity", json={**ALEX, "name": "Élodie Lefèvre-Çelik"})

    disposition = client.get("/api/cv/fr/pdf").headers["content-disposition"]

    assert disposition == 'inline; filename="cv-elodie-lefevre-celik.pdf"'


@needs_engine
def test_the_photo_goes_on_the_page_only_with_its_option(client: TestClient):
    _save_cv(client)
    _upload(client, jpeg_bytes())

    def images() -> int:
        pdf = client.get("/api/cv/fr/pdf").content
        return len(PdfReader(io.BytesIO(pdf)).pages[0].images)

    assert images() == 0
    _choose(client, [], photo=True)
    assert images() == 1
    client.delete("/api/identity/photo")
    assert images() == 0


@needs_engine
def test_a_cv_over_one_page_is_served_and_counted(client: TestClient):
    long_cv = "## Expériences\n\n" + "\n\n".join(
        f"### Société {n} — Développeur — 2000 – 2001\n\n"
        + "\n".join(f"- Réalisation {b} chez {n}" for b in range(8))
        for n in range(10)
    )
    _save_cv(client, long_cv)

    response = client.get("/api/cv/fr/pdf")

    assert response.status_code == 200
    assert int(response.headers["x-page-count"]) > 1


@needs_engine
def test_items_cut_from_the_panel_are_counted(client: TestClient):
    _save_cv(client)
    assert client.get("/api/cv/fr/pdf").headers["x-missing-items"] == "0"

    skills = "\n".join(f"- Compétence numéro {n}" for n in range(70))
    _save_cv(client, f"## Compétences\n\n{skills}\n")

    response = client.get("/api/cv/fr/pdf")
    assert response.headers["x-page-count"] == "1"
    assert int(response.headers["x-missing-items"]) > 0

    _choose(client, [], panneau_competences=False)
    assert client.get("/api/cv/fr/pdf").headers["x-missing-items"] == "0"


def test_a_render_failure_says_so_and_changes_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    _save_cv(client)
    client.put("/api/identity", json=ALEX)
    _choose(client, ["skill-java"])

    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("le rendu a échoué pour Alex Moreau")

    monkeypatch.setattr(cv_page, "render_cv", fail)
    with caplog.at_level(logging.DEBUG):
        response = client.get("/api/cv/fr/pdf")

    assert response.status_code == 503
    assert "PDF" in response.json()["message"]
    assert "Alex" not in response.text
    assert "Alex" not in caplog.text
    assert "RuntimeError" in caplog.text
    assert client.get("/api/cv/fr/selection").json()["excluded_ids"] == ["skill-java"]


# --- what is stored and logged ----------------------------------------------------


@pytest.fixture
def identity_saved(client: TestClient) -> Iterator[None]:
    _save_cv(client)
    client.put("/api/identity", json=ALEX)
    _upload(client, jpeg_bytes())
    _choose(client, ["skill-java"], photo=True)
    yield


@needs_engine
@pytest.mark.usefixtures("identity_saved")
def test_no_identity_in_the_stored_selection(client: TestClient, conn: Conn):
    client.get("/api/cv/fr/pdf")

    rows = conn.execute("SELECT * FROM cv_selections").fetchall()

    assert len(rows) == 1
    stored = str(rows[0])
    for value in ALEX.values():
        assert value not in stored
    assert set(rows[0]) == {
        "user_id",
        "lang",
        "excluded_ids",
        "photo",
        "panneau_competences",
        "loisirs",
        "updated_at",
    }


@needs_engine
def test_no_identity_value_or_pdf_content_in_any_log(
    client: TestClient, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level(logging.DEBUG):
        _save_cv(client)
        client.put("/api/identity", json=ALEX)
        _upload(client, jpeg_bytes())
        client.put("/api/identity", json={**ALEX, "name": "x" * 301})  # refused: a 422
        _choose(client, ["skill-java"], photo=True)
        assert client.get("/api/cv/fr/pdf").status_code == 200

    # httpx logs the URLs; nothing else may appear, and these never.
    for value in ALEX.values():
        assert value not in caplog.text
    assert "Nordlys" not in caplog.text

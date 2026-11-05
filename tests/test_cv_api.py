from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from jobingo.config import Settings
from jobingo.db import Conn
from jobingo.domain.profile import parse_cv_markdown
from jobingo.services import cv_editor
from jobingo.services.accounts import ensure_account
from jobingo.services.cv import StoredCv, load_cv
from jobingo_api.main import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "cv.fr.md"
TYPED = "## Résumé\nUn résumé.\n\n## Expériences\n### Acme — Dev — 2020\n* Un projet #python\n"


def _text(text: str) -> dict[str, str]:
    return {"mode": "text", "text": text}


def _save(client: TestClient, draft: dict[str, Any], sha: str | None) -> dict[str, Any]:
    response = client.put("/api/cv/fr", json={"draft": draft, "expected_sha256": sha})
    assert response.status_code == 200, response.text
    return response.json()


def _stored(conn: Conn, settings: Settings) -> str:
    user = ensure_account(conn, settings.account_username)
    stored = load_cv(conn, user.id, "fr")
    assert stored is not None
    return stored.content


def test_a_new_account_gets_an_empty_document(client: TestClient):
    response = client.get("/api/cv/fr")

    assert response.status_code == 200
    document = response.json()
    assert (document["version"], document["sha256"], document["updated_at"]) == (0, None, None)
    assert document["text"] == "" and document["diagnostics"] == []
    assert document["fields"]["experiences"] == []


def test_only_french_is_exposed(client: TestClient):
    assert client.get("/api/cv/en").status_code == 422


def test_a_saved_cv_comes_back_in_both_views_without_ids(client: TestClient):
    saved = _save(client, _text(TYPED), None)

    assert saved["version"] == 1 and saved["sha256"]
    loaded = client.get("/api/cv/fr").json()
    assert loaded == saved
    assert "<!--" not in loaded["text"] and "id=" not in str(loaded["fields"])
    assert "- Un projet #python" in loaded["text"]
    assert loaded["fields"]["experiences"][0]["company"] == "Acme"
    assert loaded["fields"]["experiences"][0]["bullets"] == ["Un projet #python"]


def test_the_stored_cv_survives_a_restart(settings: Settings, conn: Conn):
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as first:
        saved = _save(first, _text(TYPED), None)
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as second:
        assert second.get("/api/cv/fr").json() == saved


def test_both_modes_store_the_same_canonical_form(
    client: TestClient, conn: Conn, settings: Settings
):
    saved = _save(client, _text(TYPED), None)
    from_text = _stored(conn, settings)

    again = _save(client, {"mode": "form", "fields": saved["fields"]}, saved["sha256"])

    assert again["version"] == 1  # nothing changed: no new version
    assert _stored(conn, settings) == from_text


def test_a_save_of_the_fixture_from_either_view_changes_nothing(client: TestClient):
    fixture = FIXTURE.read_text(encoding="utf-8")
    saved = _save(client, _text(fixture), None)

    assert _save(client, _text(saved["text"]), saved["sha256"])["version"] == 1
    form = {"mode": "form", "fields": saved["fields"]}
    assert _save(client, form, saved["sha256"])["version"] == 1


def test_a_real_change_adds_a_version_and_ids_stay_stable(
    client: TestClient, conn: Conn, settings: Settings
):
    saved = _save(client, _text(TYPED), None)
    ids = {item.text: item.id for item in parse_cv_markdown(_stored(conn, settings)).items}

    changed = saved["text"].replace("Un projet", "Un grand projet")
    second = _save(client, _text(changed), saved["sha256"])

    assert second["version"] == 2 and second["sha256"] != saved["sha256"]
    after = {item.text: item.id for item in parse_cv_markdown(_stored(conn, settings)).items}
    assert after["Un grand projet"] == ids["Un projet"]


def test_a_removed_id_is_never_given_again(client: TestClient, conn: Conn, settings: Settings):
    saved = _save(client, _text(TYPED), None)
    removed = next(
        item.id
        for item in parse_cv_markdown(_stored(conn, settings)).items
        if item.text == "Un projet"
    )

    without = _save(
        client, _text(saved["text"].replace("- Un projet #python\n", "")), saved["sha256"]
    )
    assert "retired" not in without["text"] and without["fields"]["front"] == ""
    with_new = without["text"] + "- Sans aucun rapport\n"
    _save(client, _text(with_new), without["sha256"])

    profile = parse_cv_markdown(_stored(conn, settings))
    assert removed not in profile.ids() and len(profile.ids()) == len(profile.items)


def test_a_stale_save_is_a_conflict_that_gives_the_current_version(client: TestClient):
    first = _save(client, _text(TYPED), None)
    elsewhere = _save(client, _text(TYPED + "\n## Loisirs\n- Vélo\n"), first["sha256"])

    response = client.put(
        "/api/cv/fr",
        json={"draft": _text("## Résumé\nÉcrasé ?\n"), "expected_sha256": first["sha256"]},
    )

    assert response.status_code == 409
    assert response.json()["current"] == elsewhere
    assert client.get("/api/cv/fr").json() == elsewhere


def test_a_first_save_conflicts_when_a_cv_appeared_meanwhile(client: TestClient):
    _save(client, _text(TYPED), None)

    response = client.put("/api/cv/fr", json={"draft": _text("x"), "expected_sha256": None})

    assert response.status_code == 409


def test_two_saves_at_once_cannot_both_win(
    client: TestClient, conn: Conn, settings: Settings, monkeypatch: pytest.MonkeyPatch
):
    """The hash check passes for both: the version's unique key decides."""
    saved = _save(client, _text(TYPED), None)
    user = ensure_account(conn, settings.account_username)
    stale = load_cv(conn, user.id, "fr")
    assert stale is not None
    _save(client, _text(TYPED + "\n## Loisirs\n- Vélo\n"), saved["sha256"])
    reads: list[StoredCv | None] = [stale]
    real_load = cv_editor.load_cv

    def load_stale_once(*args: Any) -> StoredCv | None:
        return reads.pop() if reads else real_load(*args)

    monkeypatch.setattr(cv_editor, "load_cv", load_stale_once)

    response = client.put(
        "/api/cv/fr", json={"draft": _text("## Résumé\nx\n"), "expected_sha256": saved["sha256"]}
    )

    assert response.status_code == 409
    assert response.json()["current"]["version"] == 2


def test_a_duplicate_id_blocks_the_save(client: TestClient):
    text = "## Résumé\n\n\nUn. <!-- id=a -->\nDeux. <!-- id=a -->\n"

    response = client.put("/api/cv/fr", json={"draft": _text(text), "expected_sha256": None})

    assert response.status_code == 400
    found = response.json()["diagnostics"]
    assert [(d["line_no"], d["code"]) for d in found] == [(5, "duplicate_id")]  # as typed
    assert client.get("/api/cv/fr").json()["version"] == 0


def test_other_diagnostics_do_not_block_the_save(client: TestClient):
    saved = _save(client, _text("## Résumé\nJoignez-moi : alex@example.fr\n\n## Autre\nx\n"), None)

    assert saved["version"] == 1
    assert {d["code"] for d in saved["diagnostics"]} == {"personal_email", "unknown_section"}


def test_a_broken_front_matter_saves_too(client: TestClient):
    saved = _save(client, _text("---\nlang: [\n---\n\n## Résumé\nx\n"), None)

    assert saved["version"] == 1
    assert [d["code"] for d in saved["diagnostics"]] == ["invalid_front_matter"]


def test_a_dropped_keyword_is_reported_when_saving_the_form(client: TestClient):
    fields = client.get("/api/cv/fr").json()["fields"]
    fields["experiences"] = [
        {
            "company": "A",
            "role": "B",
            "start": "",
            "end": "",
            "title": "",
            "structured": True,
            "tags": ["3d"],
            "bullets": [],
        }
    ]

    saved = _save(client, {"mode": "form", "fields": fields}, None)

    assert [d["code"] for d in saved["diagnostics"]] == ["invalid_tag"]


class TestConvert:
    def test_converting_stores_nothing(self, client: TestClient):
        response = client.post("/api/cv/fr/convert", json={"draft": _text(TYPED)})

        assert response.status_code == 200
        assert response.json()["fields"]["experiences"][0]["role"] == "Dev"
        assert client.get("/api/cv/fr").json()["version"] == 0

    def test_text_to_form_and_back_keeps_everything(self, client: TestClient):
        typed = TYPED + "\n## Publications\n\nUn article.\n"
        as_form = client.post("/api/cv/fr/convert", json={"draft": _text(typed)}).json()
        assert as_form["fields"]["others"] == ["## Publications\n\nUn article."]

        back = client.post(
            "/api/cv/fr/convert", json={"draft": {"mode": "form", "fields": as_form["fields"]}}
        ).json()

        assert back["text"] == as_form["text"]
        assert "Un article." in back["text"] and "- Un projet #python" in back["text"]
        assert back["fields"] == as_form["fields"]
        assert "<!--" not in back["text"]

    def test_the_view_is_what_a_save_shows(self, client: TestClient):
        converted = client.post("/api/cv/fr/convert", json={"draft": _text(TYPED)}).json()

        saved = _save(client, _text(TYPED), None)

        assert converted["text"] == saved["text"] and converted["fields"] == saved["fields"]

    def test_diagnostics_of_a_text_draft_use_its_own_line_numbers(self, client: TestClient):
        # The blank lines disappear from the canonical layout, not from what the user sees.
        typed = "## Résumé\n\n\n\nJoignez-moi : a@b.fr\n"
        found = client.post("/api/cv/fr/convert", json={"draft": _text(typed)}).json()[
            "diagnostics"
        ]
        assert [(d["line_no"], d["code"]) for d in found] == [(5, "personal_email")]

    def test_diagnostics_of_a_form_draft_use_the_returned_text(self, client: TestClient):
        fields = client.post(
            "/api/cv/fr/convert",
            json={"draft": _text("## Loisirs\n\n\n- x\n- Vélo\n\n## Résumé\nTexte a@b.fr\n")},
        ).json()["fields"]

        view = client.post(
            "/api/cv/fr/convert", json={"draft": {"mode": "form", "fields": fields}}
        ).json()

        line = view["text"].splitlines()[view["diagnostics"][0]["line_no"] - 1]
        assert "a@b.fr" in line

    def test_a_broken_draft_still_answers(self, client: TestClient):
        response = client.post("/api/cv/fr/convert", json={"draft": _text("---\na: [\n---\nx")})
        assert response.status_code == 200
        assert response.json()["diagnostics"][0]["code"] == "invalid_front_matter"

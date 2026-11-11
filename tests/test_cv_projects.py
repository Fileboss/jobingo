"""The « Projets personnels » section: one line per project, through every view of the
CV, the selection, the model's proposal and the PDF."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobingo.db import Conn
from jobingo.domain.cv_diagnostics import diagnose_cv
from jobingo.domain.cv_fields import fields_to_markdown, parse_fields
from jobingo.domain.cv_markdown import normalize_cv, to_clean_view
from jobingo.domain.cv_proposal import CvProposal, review_proposal, short_ids
from jobingo.domain.cv_selection import DEFAULT_OPTIONS, build_selection
from jobingo.domain.identity import Identity
from jobingo.domain.profile import parse_cv_markdown
from jobingo.domain.style import StyleGuide
from jobingo.render.cv import load_manifest, render_cv
from jobingo.render.pdf import engine_available
from jobingo.render.verify import compact, extract_pdf_text, verify_cv_pdf

FIXTURE = (Path(__file__).parent / "fixtures" / "cv.fr.md").read_text(encoding="utf-8")
PROJECTS = """
## Projets personnels

- Suivi de dépenses en Django <!-- id=project-1 tags=django -->
- Station météo sur nano-ordinateur <!-- id=project-2 -->
- Jeu de société en ligne <!-- id=project-3 -->
- Bot de veille technologique <!-- id=project-4 -->
"""
WITH_PROJECTS = FIXTURE + PROJECTS
MANIFEST = load_manifest()


@pytest.mark.parametrize("title", ["Projets personnels", "Projets", "Side projects"])
def test_the_section_is_known_under_its_names(title: str):
    typed = FIXTURE + f"\n## {title}\n\n- Bot de veille\n"
    profile = parse_cv_markdown(normalize_cv(typed, FIXTURE))
    assert [item.kind for item in profile.items][-1] == "project"
    assert not [d for d in diagnose_cv(typed) if d.code == "unknown_section"]


def test_a_project_gets_a_readable_id_and_survives_the_form():
    stored = normalize_cv(FIXTURE + "\n## Projets personnels\n\n- Bot de veille\n", FIXTURE)
    [project] = [i for i in parse_cv_markdown(stored).items if i.kind == "project"]
    assert project.id.startswith("project-")

    clean = to_clean_view(stored)
    fields = parse_fields(clean)
    assert fields.projects == ["Bot de veille"]
    assert fields.others == []
    assert fields_to_markdown(fields) == clean


def test_the_page_lists_projects_and_leaves_out_those_unticked():
    profile = parse_cv_markdown(WITH_PROJECTS)
    selection = build_selection(
        profile, {"project-2"}, DEFAULT_OPTIONS, template="panneau-lateral", lang="fr"
    )
    assert [item.id for item in selection.projets] == ["project-1", "project-3", "project-4"]


def test_the_model_picks_projects_by_alias_within_the_template_limit():
    profile = parse_cv_markdown(WITH_PROJECTS)
    aliases = short_ids(profile.items)
    assert aliases["project-1"] == "R1"
    limit = MANIFEST.limits("projets").max_items
    assert limit == 3

    proposal = CvProposal.model_validate(
        {"projets": ["project-4", "project-1", "project-2", "project-3"]}
    )
    tailored = review_proposal(proposal, profile, MANIFEST, StyleGuide())

    assert [item.id for item in tailored.projets] == ["project-4", "project-1", "project-2"]
    assert [d.id for d in tailored.discarded] == ["project-3"]


@pytest.mark.skipif(not engine_available(), reason="WeasyPrint needs Pango")
@pytest.mark.parametrize("panel", [True, False])
def test_projects_are_printed_under_the_experiences(panel: bool):
    selection = build_selection(
        parse_cv_markdown(WITH_PROJECTS),
        set(),
        DEFAULT_OPTIONS.model_copy(update={"panneau_competences": panel}),
        template="panneau-lateral",
        lang="fr",
    )
    pdf = render_cv(selection, Identity(name="Alex Moreau")).pdf

    assert verify_cv_pdf(pdf, selection) == []
    text = compact(extract_pdf_text(pdf))
    assert text.index(compact("Projets personnels")) < text.index(compact("Formation"))


def test_projects_written_before_the_section_was_known_wait_for_one_save(
    client: TestClient, conn: Conn
):
    """Saved while « Projets personnels » was an unknown section, its lines have no id:
    the editor says a save carries them forward, with no edit to make."""
    current = client.get("/api/cv/fr").json()
    client.put(
        "/api/cv/fr",
        json={"draft": {"mode": "text", "text": FIXTURE}, "expected_sha256": current["sha256"]},
    )
    saved = client.get("/api/cv/fr").json()
    assert saved["needs_save"] is False
    user = conn.execute("SELECT id FROM users").fetchone()
    assert user is not None
    row = conn.execute(
        "SELECT content FROM cv_versions WHERE user_id = %s ORDER BY version DESC LIMIT 1",
        (user["id"],),
    ).fetchone()
    assert row is not None
    old: str = row["content"]
    conn.execute(
        "INSERT INTO cv_versions (user_id, lang, version, content) VALUES (%s, 'fr', %s, %s)",
        (user["id"], saved["version"] + 1, old + "\n## Projets personnels\n\n- Bot de veille\n"),
    )

    before = client.get("/api/cv/fr").json()
    assert before["needs_save"] is True
    after = client.put(
        "/api/cv/fr",
        json={
            "draft": {"mode": "text", "text": before["text"]},
            "expected_sha256": before["sha256"],
        },
    ).json()

    assert after["needs_save"] is False
    assert after["fields"]["projects"] == ["Bot de veille"]
    assert client.get("/api/cv/fr/selection").json()["projets"][0]["text"] == "Bot de veille"

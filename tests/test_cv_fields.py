from pathlib import Path

import pytest

from jobingo.domain.cv_fields import (
    UNTITLED_EXPERIENCE,
    CvFields,
    ExperienceFields,
    FormationEntry,
    canonical_stored,
    fields_to_markdown,
    parse_fields,
    split_tags,
)
from jobingo.domain.cv_markdown import normalize_cv, to_clean_view
from jobingo.domain.profile import parse_cv_markdown

FIXTURE = Path(__file__).parent / "fixtures" / "cv.fr.md"


def test_the_fixture_goes_through_the_form_and_back_unchanged():
    stored = FIXTURE.read_text(encoding="utf-8")
    clean = to_clean_view(stored)
    fields = parse_fields(clean)
    assert fields.others == []
    assert [e.company for e in fields.experiences] == ["Nordlys", "Batiflux", "Colibri Conseil"]
    first = fields.experiences[0]
    assert (first.role, first.start, first.end) == (
        "Ingénieur backend senior",
        "01/2022",
        "08/2026",
    )
    assert first.tags == ["python", "data"] and first.bullets[0].startswith("Migration")
    assert fields_to_markdown(fields) == clean
    # ...and the stored CV is byte for byte what it was: a save without edit is a no-op.
    assert normalize_cv(fields_to_markdown(fields), stored) == stored


def test_content_the_form_cannot_show_is_written_back_untouched():
    clean = (
        "Un mot avant toute section.\n\n"
        "## Résumé\n\nUn résumé.\n\n"
        "## Publications\n\nUne ligne libre.\n- Une puce <!-- garde-moi -->\n\n"
        "## Compétences\n\n- Python\n\n"
        "## Compétences\n\n- Rust\n\n"
        "## Loisirs\n\n- Natation\nune ligne qui n'est pas une puce\n"
    )
    fields = parse_fields(clean)
    assert fields.resume == "Un résumé." and fields.skills == ["Python"]
    assert fields.before == "Un mot avant toute section."
    assert fields.others == [
        "## Publications\n\nUne ligne libre.\n- Une puce <!-- garde-moi -->",
        "## Compétences\n\n- Rust",
        "## Loisirs\n\n- Natation\nune ligne qui n'est pas une puce",
    ]
    assert fields.order == ["resume", "other", "skills", "other", "other"]
    assert fields_to_markdown(fields) == clean  # every block back at its place


def test_a_title_is_split_only_when_joining_gives_the_same_text():
    clean = (
        "## Expériences\n\n"
        "### A — B — 03/2021 – 06/2025\n\n- x\n\n"
        "### A — B — 03/2021 - 06/2025\n\n- y\n\n"
        "### Freelance, 2019\n\n- z\n\n"
        "### A — B — C — D\n\n- w\n"
    )
    first, hyphen, free, four = parse_fields(clean).experiences
    assert first.structured and (first.start, first.end) == ("03/2021", "06/2025")
    assert hyphen.structured and (hyphen.start, hyphen.end) == ("03/2021 - 06/2025", "")
    for experience in (free, four):
        assert not experience.structured
    assert free.title == "Freelance, 2019"
    assert fields_to_markdown(parse_fields(clean)) == clean


@pytest.mark.parametrize(
    "experience",
    [
        ExperienceFields(company="Acme", role="Dev"),
        ExperienceFields(company="Acme", start="2020"),
        ExperienceFields(company="Acme", start="2020", end="2021"),
    ],
)
def test_partly_filled_titles_come_back_in_the_same_fields(experience: ExperienceFields):
    fields = CvFields(experiences=[experience])
    assert parse_fields(fields_to_markdown(fields)).experiences == [experience]


def test_keywords_take_a_hash_or_not_and_bad_ones_are_reported():
    assert split_tags(["python", "#api, data"]) == (["python", "api", "data"], [])
    assert split_tags(["3d", "ok"]) == (["ok"], ["3d"])


def test_an_experience_without_title_keeps_its_achievements():
    fields = CvFields(experiences=[ExperienceFields(bullets=["une réalisation"])])
    written = fields_to_markdown(fields)
    assert written == f"## Expériences\n\n### {UNTITLED_EXPERIENCE}\n\n- une réalisation\n"
    assert parse_fields(written).others == []


def test_an_empty_row_is_dropped():
    assert fields_to_markdown(CvFields(experiences=[ExperienceFields()])) == ""


def test_typed_bullet_markers_and_blank_lines_are_tidied():
    fields = CvFields(
        experiences=[
            ExperienceFields(
                title="Solo", structured=False, bullets=["- un", "", "* deux\n3. trois"]
            )
        ]
    )
    clean = fields_to_markdown(fields)
    assert "### Solo\n\n- un\n- deux\n- trois\n" in clean
    assert [i.text for i in parse_cv_markdown(normalize_cv(clean)).items if i.kind == "bullet"] == [
        "un",
        "deux",
        "trois",
    ]


def test_a_line_break_in_a_title_field_does_not_split_the_title():
    fields = CvFields(experiences=[ExperienceFields(company="A\nB", role="C")])
    assert fields_to_markdown(fields) == "## Expériences\n\n### A B — C\n"


def test_the_front_matter_is_kept_and_written_for_another_language():
    fields = CvFields(front="---\nlang: en\n---\n", resume="Hello")
    assert fields_to_markdown(fields).startswith("---\nlang: en\n---\n\n## Résumé")
    english = fields_to_markdown(CvFields(resume="Hello"), "en")
    assert english.startswith("---\nlang: en\n---\n")
    assert parse_cv_markdown(normalize_cv(english)).lang == "en"


def test_formation_keeps_h3_entries_and_bullets():
    clean = "## Formation\n\n### Master, X (2019)\n- Licence, Y (2017)\n"
    fields = parse_fields(clean)
    assert fields.formation == [
        FormationEntry(text="Master, X (2019)", heading=True),
        FormationEntry(text="Licence, Y (2017)"),
    ]
    assert fields.others == []
    stored = normalize_cv(fields_to_markdown(fields))
    items = parse_cv_markdown(stored).items
    assert [i.text for i in items] == ["Master, X (2019)", "Licence, Y (2017)"]


# The invariant: the form and the Markdown are the same thing (see cv_fields).
VARIED = [
    FIXTURE.read_text(encoding="utf-8"),
    "## Compétences\n* Python\n\n## Expériences\n\n**Nordlys — Ingénieur — 2022 – 2026**\n"
    "1. Migration\n2) Coûts\n\n## Résumé\n\nLigne un.\n\n\nLigne deux.\n",
    "## Expériences\n\n- Nordlys — Ingénieur — 2022\n  - Migration\n    - détail\n",
    "Avant.\n\n## Résumé\nTexte.\n## Publications\n\n- Un article\n\n## Loisirs\n\n- Vélo\n",
    "## Expériences\n\nTexte sans puce\n### A — B — 2020\n- x\n\n"
    "## Compétences\n\n- Python\n\n## Compétences\n\n- Rust\n",
    "# Mon CV\n\n## Summary\nHello\n## Skills\n- Go #go\n",
    "---\nlang: en\n---\n## Experience\n### X\n- y #a #b\n",
    "## Formation\n\n### École — 2015\n- Master\n\n## Loisirs\n- Vélo\nune ligne\n",
    "---\nlang: [\n---\n\n## Résumé\nTexte.\n",
    "---\n\n## Résumé\nPas de fin de bloc.\n",
    "## Compétences\n- - Python\n",
    "",
]


def _content(stored: str) -> list[tuple[str, str, str]]:
    return [(item.id, item.kind, item.text) for item in parse_cv_markdown(stored).items]


@pytest.mark.parametrize("typed", VARIED)
def test_what_a_save_stores_is_a_fixed_point_of_the_form(typed: str):
    stored = canonical_stored(typed, "")
    clean = to_clean_view(stored)
    assert fields_to_markdown(parse_fields(clean)) == clean
    assert canonical_stored(clean, stored) == stored  # text saved as shown
    assert canonical_stored(stored, stored) == stored  # stored form saved as shown


@pytest.mark.parametrize("typed", [text for text in VARIED if "- - " not in text])
def test_nothing_is_lost_or_reordered_on_the_way(typed: str):
    # Only the layout is the form's.
    stored = canonical_stored(typed, "")
    assert [(k, t) for _i, k, t in _content(stored)] == [
        (k, t) for _i, k, t in _content(normalize_cv(typed, ""))
    ]


def test_the_fixed_point_holds_with_retired_ids():
    first = canonical_stored("## Résumé\nUn.\n\n## Loisirs\n- Vélo\n- Voile\n", "")
    second = canonical_stored("## Résumé\nUn.\n\n## Loisirs\n- Vélo\n", first)
    assert "retired" in second
    clean = to_clean_view(second)
    assert fields_to_markdown(parse_fields(clean)) == clean
    assert canonical_stored(clean, second) == second


def test_the_sections_keep_the_order_of_the_document():
    clean = "## Compétences\n\n- Python\n\n## Publications\n\n- Un article\n\n## Résumé\n\nTexte.\n"
    fields = parse_fields(clean)
    assert fields.order == ["skills", "other", "resume"]
    assert fields_to_markdown(fields) == clean


def test_a_section_new_to_the_document_goes_at_its_usual_place():
    fields = parse_fields("## Résumé\n\nTexte.\n\n## Compétences\n\n- Python\n")
    fields.experiences = [ExperienceFields(company="A", role="B", start="2020")]
    fields.hobbies = ["Vélo"]
    written = fields_to_markdown(fields)
    order = [written.index(title) for title in ("Résumé", "Expériences", "Compétences", "Loisirs")]
    assert order == sorted(order)


def test_the_resume_keeps_its_paragraphs():
    clean = "## Résumé\n\nLigne un.\n\nLigne deux.\nLigne trois.\n"
    assert parse_fields(clean).resume == "Ligne un.\n\nLigne deux.\nLigne trois."
    assert fields_to_markdown(parse_fields(clean)) == clean

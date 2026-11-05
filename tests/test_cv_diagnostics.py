from jobingo.domain.cv_diagnostics import diagnose_cv, diagnose_fields
from jobingo.domain.cv_fields import UNTITLED_EXPERIENCE, CvFields, ExperienceFields


def _codes(text: str) -> list[tuple[int, str]]:
    return [(d.line_no, d.code) for d in diagnose_cv(text)]


def test_a_clean_cv_has_no_diagnostic():
    assert _codes("## Résumé\nTexte.\n\n## Compétences\n- Python #python\n") == []


def test_each_unreadable_line_is_reported_with_its_line_number():
    text = (
        "# Alex\n"  # 1
        "avant\n"  # 2
        "## Expériences\n"  # 3
        "- sans expérience\n"  # 4
        "### A — B — 2020\n"  # 5
        "une ligne\n"  # 6
        "## Compétences\n"  # 7
        "### titre\n"  # 8
        "## Publications\n"  # 9
    )
    assert _codes(text) == [
        (1, "title_line"),
        (2, "outside_section"),
        (4, "orphan_bullet"),
        (6, "unrecognized_line"),
        (8, "heading_outside"),
        (9, "unknown_section"),
    ]


def test_line_numbers_count_the_front_matter():
    assert _codes("---\nlang: fr\n---\n\n## Résumé\nx\n## Formation\nligne\n") == [
        (8, "unrecognized_line")
    ]


def test_a_broken_front_matter_is_one_diagnostic_not_a_failure():
    found = diagnose_cv("---\nlang: [\n---\n\n## Résumé\nx\n")
    assert [d.code for d in found] == ["invalid_front_matter"]
    assert found[0].level == "error"


def test_personal_data_is_flagged_with_the_value_and_its_section():
    text = (
        "## Résumé\nx\n\n## Loisirs\n- Contact alex@example.fr\n- 06 12 34 56 78\n- github.com/a\n"
    )
    found = diagnose_cv(text)
    assert [(d.line_no, d.code, d.section) for d in found] == [
        (5, "personal_email", "Loisirs"),
        (6, "personal_phone", "Loisirs"),
        (7, "personal_url", "Loisirs"),
    ]
    assert "« alex@example.fr »" in found[0].message
    assert all(d.level == "warning" for d in found)


def test_a_duplicate_id_is_an_error():
    found = diagnose_cv("## Résumé\nUn. <!-- id=a -->\nDeux. <!-- id=a -->\n")
    assert [(d.line_no, d.code, d.level) for d in found] == [(3, "duplicate_id", "error")]


def test_an_untitled_experience_is_flagged():
    found = _codes(f"## Expériences\n\n### {UNTITLED_EXPERIENCE}\n\n- x\n")
    assert found == [(3, "missing_title")]


def test_a_keyword_the_form_cannot_write_is_flagged_without_a_line():
    fields = CvFields(experiences=[ExperienceFields(company="A", tags=["3d", "ok"])])
    found = diagnose_fields(fields)
    assert [(d.line_no, d.code, d.section) for d in found] == [(0, "invalid_tag", "Expériences")]
    assert "3d" in found[0].message

from jobingo.domain.profile import parse_cv_markdown

CV_OK = """---
lang: fr
---

## Résumé
Texte libre, réécrit à la demande. <!-- id=resume -->

## Expériences

### Ingénieur logiciel, Acme (2021-03 à 2025-06) <!-- id=acme sector=fintech -->

- A migré le pipeline de facturation. <!-- id=acme-01 tags=python,migration,cloud -->
- A encadré deux alternants. <!-- id=acme-02 tags=mentorat,api -->

## Formation
### Master informatique, Université X (2019) <!-- id=edu-01 -->

## Compétences
- Python, SQL, FastAPI <!-- id=skill-01 tags=python,sql -->
"""


def test_parses_valid_cv_with_no_errors():
    profile = parse_cv_markdown(CV_OK)
    assert profile.lang == "fr"
    assert profile.is_valid
    assert profile.errors == []
    assert profile.ids() == {"resume", "acme", "acme-01", "acme-02", "edu-01", "skill-01"}


def test_bullet_inherits_parent_experience_id():
    profile = parse_cv_markdown(CV_OK)
    bullet = next(item for item in profile.items if item.id == "acme-01")
    assert bullet.parent_id == "acme"
    assert bullet.tags == ["python", "migration", "cloud"]


def test_duplicate_id_is_rejected_with_line_number():
    duplicated = CV_OK.replace(
        "- A encadré deux alternants. <!-- id=acme-02 tags=mentorat,api -->",
        "- A encadré deux alternants. <!-- id=acme-01 tags=mentorat,api -->",
    )
    profile = parse_cv_markdown(duplicated)
    assert not profile.is_valid
    duplicate_errors = [e for e in profile.errors if e.kind == "duplicate_id"]
    assert len(duplicate_errors) == 1
    lines = duplicated.splitlines()
    expected_line = next(
        i for i, line in enumerate(lines, start=1) if "id=acme-01 tags=mentorat" in line
    )
    assert duplicate_errors[0].line_no == expected_line


def test_missing_id_is_flagged_but_not_blocking():
    missing = CV_OK.replace(
        "- A encadré deux alternants. <!-- id=acme-02 tags=mentorat,api -->",
        "- A encadré deux alternants.",
    )
    profile = parse_cv_markdown(missing)
    assert profile.is_valid  # missing id doesn't block, only duplicates do
    missing_errors = [e for e in profile.errors if e.kind == "missing_id"]
    assert len(missing_errors) == 1


def test_a_broken_front_matter_does_not_stop_the_parser():
    profile = parse_cv_markdown("---\nlang: [\n---\n\n## Résumé\nTexte. <!-- id=r -->\n")
    assert profile.ids() == {"r"}

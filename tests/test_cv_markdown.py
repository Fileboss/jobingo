from pathlib import Path

from jobingo.domain.cv_markdown import normalize_cv, to_clean_view
from jobingo.domain.profile import Profile, ProfileItem, parse_cv_markdown

FIXTURE = Path(__file__).parent / "fixtures" / "cv.fr.md"

TYPED = """## résumé
Ingénieur backend, huit ans de plateformes de données.

## Experience
### Nordlys — Ingénieur backend — 01/2022 – 08/2026 #python #data
* Migration de 120 tâches ETL vers Airflow #airflow
- Réduction de 40 % du coût de l'entrepôt

### Batiflux — Développeur — 2018 – 2021
- Refonte du module de devis

## Formation
### Master informatique, Université X (2019)

## Skills
- Python, SQL #python
"""


def _by_text(profile: Profile) -> dict[str, ProfileItem]:
    return {item.text: item for item in profile.items}


def test_a_cv_typed_without_any_id_is_stored_with_readable_ids_and_tags():
    stored = normalize_cv(TYPED)
    profile = parse_cv_markdown(stored)
    assert profile.errors == []
    items = _by_text(profile)
    nordlys = items["Nordlys — Ingénieur backend — 01/2022 – 08/2026"]
    assert nordlys.id == "nordlys" and nordlys.tags == ["python", "data"]
    bullet = items["Migration de 120 tâches ETL vers Airflow"]
    assert bullet.id == "nordlys-01" and bullet.parent_id == "nordlys"
    assert bullet.tags == ["airflow"] and bullet.kind == "bullet"
    assert items["Python, SQL"].kind == "skill" and items["Python, SQL"].section == "Compétences"
    assert items["Master informatique, Université X (2019)"].kind == "formation"
    assert len(profile.ids()) == len(profile.items)  # unique


def test_the_clean_view_has_no_html_comment_and_round_trips_to_the_same_cv():
    stored = normalize_cv(TYPED)
    clean = to_clean_view(stored)
    assert "<!--" not in clean and "#python #data" in clean
    assert normalize_cv(clean, stored) == stored  # idempotent, ids stable


def test_a_stored_cv_is_unchanged_by_a_save_without_edit():
    stored = FIXTURE.read_text(encoding="utf-8")
    assert normalize_cv(stored, stored) == stored
    clean = to_clean_view(stored)
    assert "<!--" not in clean
    assert parse_cv_markdown(normalize_cv(clean, stored)).ids() == parse_cv_markdown(stored).ids()


def test_an_edited_bullet_keeps_its_id_and_a_new_one_gets_a_fresh_id():
    stored = normalize_cv(TYPED)
    clean = to_clean_view(stored).replace(
        "Refonte du module de devis", "Refonte complète du module de devis"
    )
    clean = clean.replace("- Réduction", "- Nouvelle réalisation\n- Réduction")
    after = parse_cv_markdown(normalize_cv(clean, stored))
    before = parse_cv_markdown(stored)
    old = _by_text(before)["Refonte du module de devis"].id
    assert _by_text(after)["Refonte complète du module de devis"].id == old
    assert _by_text(after)["Nouvelle réalisation"].id not in before.ids()


def test_a_moved_bullet_keeps_its_id():
    stored = normalize_cv(TYPED)
    clean = to_clean_view(stored)
    clean = clean.replace("- Refonte du module de devis\n", "").replace(
        "- Réduction de 40 % du coût de l'entrepôt\n",
        "- Réduction de 40 % du coût de l'entrepôt\n- Refonte du module de devis\n",
    )
    after = _by_text(parse_cv_markdown(normalize_cv(clean, stored)))
    before = _by_text(parse_cv_markdown(stored))
    assert after["Refonte du module de devis"].id == before["Refonte du module de devis"].id
    assert after["Refonte du module de devis"].parent_id == "nordlys"


def test_a_deleted_id_is_retired_and_never_given_again():
    stored = normalize_cv(TYPED)
    removed = _by_text(parse_cv_markdown(stored))["Migration de 120 tâches ETL vers Airflow"].id
    clean = to_clean_view(stored)
    clean = clean.replace("- Migration de 120 tâches ETL vers Airflow #airflow\n", "")
    second = normalize_cv(clean, stored)
    assert f"- {removed}" in second  # listed in the front matter
    assert removed not in parse_cv_markdown(second).ids()
    again = normalize_cv(clean.replace("- Réduction", "- Autre chose\n- Réduction"), second)
    assert removed not in parse_cv_markdown(again).ids()
    assert "retired" not in to_clean_view(again)


def test_a_retired_id_pasted_back_is_not_reused():
    first = normalize_cv("## Loisirs\n- Vélo <!-- id=velo -->\n- Voile <!-- id=voile -->\n")
    second = normalize_cv("## Loisirs\n- Vélo <!-- id=velo -->\n", first)
    third = normalize_cv("## Loisirs\n- Vélo <!-- id=velo -->\n- Voile <!-- id=voile -->\n", second)
    profile = parse_cv_markdown(third)
    assert "voile" not in profile.ids() and "velo" in profile.ids()
    assert [item.text for item in profile.items] == ["Vélo", "Voile"]


def test_the_clean_view_of_a_cv_with_retired_ids_starts_like_the_typed_text():
    stored = normalize_cv("## Résumé\nUn.\n\n## Loisirs\n- Vélo\n")
    second = normalize_cv("## Résumé\nUn.\n", stored)
    assert to_clean_view(second) == "## Résumé\nUn.\n"


def test_windows_line_endings_from_the_browser_are_normalised():
    stored = normalize_cv(TYPED.replace("\n", "\r\n"))
    assert "\r" not in stored and parse_cv_markdown(stored).errors == []


def test_hand_written_ids_are_kept_and_duplicates_still_reported():
    typed = "## Résumé\nTexte. <!-- id=a -->\nAutre. <!-- id=a -->\n"
    profile = parse_cv_markdown(normalize_cv(typed))
    assert not profile.is_valid


def test_front_matter_language_is_kept_in_both_views():
    stored = normalize_cv("---\nlang: en\n---\n\n## Summary\nText.\n")
    assert parse_cv_markdown(stored).lang == "en"
    assert to_clean_view(stored).startswith("---\nlang: en\n---")


def test_a_broken_front_matter_stays_as_text_and_ids_still_retire():
    broken = "---\nlang: [\n---\n\n## Résumé\nUn.\n\n## Loisirs\n- Vélo\n"
    stored = normalize_cv(broken)
    assert stored.startswith(broken.split("## Résumé")[0])
    assert len(parse_cv_markdown(stored).items) == 2
    second = normalize_cv("---\nlang: [\n---\n\n## Résumé\nUn.\n", stored)
    assert to_clean_view(second) == "---\nlang: [\n---\n\n## Résumé\nUn.\n"


def test_hash_signs_inside_a_sentence_are_not_tags():
    typed = "## Expériences\n### Acme — Dev — 2020\n- Migration C# et F# vers .NET 8 (top #1)\n"
    stored = normalize_cv(typed)
    bullet = next(i for i in parse_cv_markdown(stored).items if i.kind == "bullet")
    assert bullet.tags == [] and "C# et F#" in bullet.text

import pytest

from jobingo.domain.personal_data import find_personal_data, redact


def test_detects_email():
    findings = find_personal_data("Contact: prenom.nom@example.org pour plus d'infos.")
    assert len(findings) == 1
    assert findings[0].kind == "email"
    assert findings[0].line_no == 1


def test_detects_french_phone_number():
    findings = find_personal_data("Tel: 06 12 34 56 78")
    assert any(f.kind == "phone" for f in findings)


def test_detects_international_phone_number():
    findings = find_personal_data("Tel: +33 6 00 00 00 00")
    assert any(f.kind == "phone" for f in findings)


@pytest.mark.parametrize(
    "text",
    [
        "Voir https://www.linkedin.com/in/pseudo",
        "Voir www.pseudo.example",
        "Voir linkedin.com/in/pseudo",
        "Voir github.com/pseudo",
    ],
)
def test_detects_profile_url(text: str):
    assert any(f.kind == "url" for f in find_personal_data(text))


def test_reports_correct_line_number():
    text = "## Résumé\nTexte libre. <!-- id=resume -->\n\n- Contact: a@b.fr <!-- id=x -->\n"
    findings = find_personal_data(text)
    assert findings[0].line_no == 4


def test_clean_cv_has_no_findings():
    text = "## Résumé\nTexte libre, réécrit à la demande. <!-- id=resume -->\n"
    assert find_personal_data(text) == []


IDENTITY = ["Camille Durand", "camille.durand@example.net", "06 12 34 56 78", "Hélène", "Morel"]


def test_redaction_leaves_words_that_merely_contain_a_value():
    text = "Morelli & Fils recrute à Saint-Morel et chez Morelstoff."
    assert redact(text, IDENTITY) == text


def test_redaction_still_replaces_the_value_as_a_word():
    assert redact("Signé : MOREL.", IDENTITY) == "Signé : [CANDIDAT]."


@pytest.mark.parametrize(
    "written", ["06 12 34 56 78", "0612345678", "06.12.34.56.78", "+33 6 12 34 56 78"]
)
def test_a_phone_matches_whatever_its_format(written: str):
    assert redact(f"Tél : {written}.", IDENTITY) == "Tél : [CANDIDAT]."


def test_a_name_matches_without_its_accents_and_across_a_line_break():
    assert redact("Bonjour Helene,", IDENTITY) == "Bonjour [CANDIDAT],"
    assert redact("Camille\nDurand", IDENTITY) == "[CANDIDAT]"


def test_a_short_number_is_not_treated_as_a_phone():
    assert redact("Référence 2026-10", ["2026-10"]) == "Référence [CANDIDAT]"
    assert redact("x", ["--------"]) == "x"

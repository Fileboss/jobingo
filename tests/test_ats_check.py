"""The ATS check's report, on a parser's answer: no parser runs here."""

import importlib.util
from pathlib import Path
from types import ModuleType


def _script() -> ModuleType:
    path = Path(__file__).parent.parent / "scripts" / "ats_check.py"
    spec = importlib.util.spec_from_file_location("ats_check", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# A trimmed answer of Affinda's parser, on the fictional CV.
ANSWER = {
    "data": {
        "person": {
            "name": {"given": "Alex", "family": "Moreau"},
            "location": {"formatted": "Montpellier, Occitanie, France"},
        },
        "contact": {
            "emails": ["alex.moreau@example.org"],
            "phoneNumbers": [{"formatted": "+33 6 00 00 00 00"}],
            "websites": [{"domain": "github.com/alexmoreau"}],
        },
        "summary": "Ingénieur backend depuis neuf ans.",
        "workExperience": [
            {
                "jobTitle": "Développeur Python",
                "organization": "Transvia Logistique",
                "dateRange": {"start": {"date": "2019-01-01"}, "end": {"date": "2022-02-01"}},
                "description": "• Développement du module Django\n• Intégration continue",
            }
        ],
        "education": [],
        "certifications": [
            {"name": "Certification Cloud", "issuer": "Nuage", "date": {"date": "2023-01-01"}}
        ],
        "skills": [{"name": "Django (Web Framework)"}],
    },
    "meta": {"document": {"extractionQuality": {"band": "high", "score": 0.95}}},
}


def test_the_report_names_each_field_and_what_is_missing():
    lines = _script().summary(ANSWER)

    assert "Nom : Alex Moreau" in lines
    assert "Téléphone : +33 6 00 00 00 00" in lines
    assert (
        "  - Développeur Python chez Transvia Logistique, 2019-01 → 2022-02, "
        "2 ligne(s) de description"
    ) in lines
    assert "Formation (0) :" in lines
    assert "  - Certification Cloud, Nuage, 2023" in lines
    assert "Langues : aucune" in lines


def test_a_field_not_found_says_so():
    lines = _script().summary({"data": {}, "meta": {}})

    assert "Nom : NON TROUVÉ" in lines and "E-mail : NON TROUVÉ" in lines

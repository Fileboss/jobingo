"""What a recruiting tool reads from a CV, by two local parsers (docs/ats-check.md).

Usage: `ats_check.py [cv.pdf] [--text] [--json]`. Without a file, it renders the fictional
CV (Alex Moreau). Tika gives the text in the order a parsing pipeline reads it; Affinda's
resume parser gives the fields an ATS would fill. Both run in Docker (`make ats-up`) with
no route out of this machine, so the CV stays here. Nothing is written to disk.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

TIKA_URL = "http://127.0.0.1:9998/tika/text"
AFFINDA_URL = "http://127.0.0.1:8090/v1/resumes/parse"
ROOT = Path(__file__).resolve().parent.parent


def tika_text(pdf: bytes) -> str:
    request = urllib.request.Request(
        TIKA_URL,
        data=pdf,
        method="PUT",
        headers={"Accept": "text/plain", "Content-Type": "application/pdf"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8")


def affinda_fields(pdf: bytes) -> dict[str, Any]:
    request = urllib.request.Request(
        AFFINDA_URL,
        data=pdf,
        method="POST",
        headers={
            "Content-Type": "application/pdf",
            "Content-Disposition": 'attachment; filename="cv.pdf"',
        },
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        parsed: dict[str, Any] = json.loads(response.read())
        return parsed


def _dates(entry: dict[str, Any]) -> str:
    period: dict[str, Any] = entry.get("dateRange") or {}

    def month(bound: str) -> str:
        found: dict[str, Any] = period.get(bound) or {}
        return str(found.get("date", "?"))[:7]

    return f"{month('start')} → {month('end')}"


def summary(parsed: dict[str, Any]) -> list[str]:
    """The fields that matter to a recruiter, one line each, and what is missing."""
    data: dict[str, Any] = parsed.get("data", {})
    meta: dict[str, Any] = parsed.get("meta", {}).get("document", {})
    person = data.get("person", {})
    contact = data.get("contact", {})
    name = " ".join(
        filter(None, [person.get("name", {}).get("given"), person.get("name", {}).get("family")])
    )
    quality = meta.get("extractionQuality", {})
    lines = [
        f"Qualité d'extraction : {quality.get('band', '?')} ({quality.get('score', '?')})",
        f"Nom : {name or 'NON TROUVÉ'}",
        f"E-mail : {', '.join(contact.get('emails', [])) or 'NON TROUVÉ'}",
        "Téléphone : "
        + (
            ", ".join(p.get("formatted", p.get("raw", "")) for p in contact.get("phoneNumbers", []))
            or "NON TROUVÉ"
        ),
        f"Lieu : {person.get('location', {}).get('formatted') or 'NON TROUVÉ'}",
        "Liens : "
        + (", ".join(w.get("domain", "") for w in contact.get("websites", [])) or "aucun"),
        f"Résumé : {'trouvé' if data.get('summary') else 'NON TROUVÉ'}",
        f"Expériences ({len(data.get('workExperience', []))}) :",
    ]
    for job in data.get("workExperience", []):
        bullets = len(
            [line for line in (job.get("description") or "").splitlines() if line.strip()]
        )
        lines.append(
            f"  - {job.get('jobTitle', '?')} chez {job.get('organization', '?')}, "
            f"{_dates(job)}, {bullets} ligne(s) de description"
        )
    lines.append(f"Formation ({len(data.get('education', []))}) :")
    for school in data.get("education", []):
        degree, place = school.get("qualification", "?"), school.get("institution", "?")
        lines.append(f"  - {degree} — {place}, {_dates(school)}")
    lines.append(f"Certifications ({len(data.get('certifications', []))}) :")
    for certification in data.get("certifications", []):
        when: dict[str, Any] = certification.get("date") or {}
        issued = str(when.get("date", "?"))[:4]
        lines.append(
            f"  - {certification.get('name', '?')}, {certification.get('issuer', '?')}, {issued}"
        )
    lines.append(f"Projets : {len(data.get('projects', []))}")
    skills = [skill.get("name", "") for skill in data.get("skills", [])]
    lines.append(f"Compétences ({len(skills)}) : {', '.join(skills)}")
    languages = [language.get("name", str(language)) for language in data.get("languages", [])]
    lines.append(f"Langues : {', '.join(languages) or 'aucune'}")
    return lines


def _fictional_cv() -> bytes:
    """Alex Moreau's CV, as the app renders it with the side panel."""
    from jobingo.domain.cv_selection import DEFAULT_OPTIONS, build_selection
    from jobingo.domain.identity import Identity
    from jobingo.domain.profile import parse_cv_markdown
    from jobingo.render.cv import render_cv

    cv = (ROOT / "evals" / "fixtures" / "cv-verbeux.fr.md").read_text(encoding="utf-8")
    profile = parse_cv_markdown(cv)
    left_out = {"fenouil", "helianthe-05", "transvia-04", "ardoise-02", "ardoise-04", "project-02"}
    left_out |= {item.id for item in profile.items if item.parent_id == "fenouil"}
    selection = build_selection(
        profile, left_out, DEFAULT_OPTIONS, template="panneau-lateral", lang="fr"
    )
    alex = Identity(
        name="Alex Moreau",
        email="alex.moreau@example.org",
        phone="+33 6 00 00 00 00",
        address="12 rue des Lilas 34000 Montpellier",
        website="https://alexmoreau.example",
        linkedin="https://www.linkedin.com/in/alexmoreau",
        github="https://github.com/alexmoreau",
    )
    return render_cv(selection, alex).pdf


def main() -> int:
    parser = argparse.ArgumentParser(description="What a recruiting tool reads from a CV.")
    parser.add_argument("pdf", nargs="?", type=Path, help="a CV's PDF; the fictional CV without it")
    parser.add_argument("--text", action="store_true", help="print the whole text Tika reads")
    parser.add_argument("--json", action="store_true", help="print Affinda's whole answer")
    args = parser.parse_args()

    pdf = args.pdf.read_bytes() if args.pdf else _fictional_cv()
    try:
        text = tika_text(pdf)
        parsed = affinda_fields(pdf)
    except (urllib.error.URLError, ConnectionError, TimeoutError) as error:
        print(f"Parseurs injoignables ({error}). Lancez `make ats-up`.", file=sys.stderr)
        return 1

    print("— Tika : le texte, dans l'ordre où il est lu —")
    lines = [line for line in text.splitlines() if line.strip()]
    print(
        "\n".join(
            lines if args.text else lines[:12] + [f"… ({len(lines)} lignes, --text pour tout)"]
        )
    )
    print("\n— Affinda : les champs qu'un ATS remplirait —")
    print("\n".join(summary(parsed)))
    if args.json:
        print(json.dumps(parsed, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""The fictional documents the README's screenshots show (`make screenshots`).

Writes into `apps/web/screenshots/.data/`, gitignored: Alex Moreau's CV as the editor
loads it, a CV adapted to a fictional offer as the diff screen shows it, a cover letter,
the real PDFs of both, and the committed eval results. Everything goes through the
domain's own functions, so the screens show what the app would; no database, no model.
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path

from jobingo.domain.cv_document import CvDocument, TextDraft, convert_draft
from jobingo.domain.cv_draft import (
    DraftView,
    OfferInput,
    draft_items,
    draft_selection,
    initial_choices,
)
from jobingo.domain.cv_proposal import (
    DiscardedItem,
    ReviewedExperience,
    ReviewedFormation,
    ReviewedItem,
    TailoredCv,
)
from jobingo.domain.cv_selection import CvOptions, OptionBlockers
from jobingo.domain.identity import Identity
from jobingo.domain.profile import parse_cv_markdown
from jobingo.render.cv import load_manifest, render_cv
from jobingo.render.letter import render_letter
from jobingo.services.letters import LetterView, SlotView
from jobingo.services.observability import eval_report

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "apps" / "web" / "screenshots" / ".data"
AT = datetime(2026, 11, 12, 9, 30, tzinfo=UTC)

ALEX = Identity(
    name="Alex Moreau",
    email="alex.moreau@example.org",
    phone="+33 6 00 00 00 00",
    address="12 rue des Lilas 34000 Montpellier",
    website="https://alexmoreau.example",
    linkedin="https://www.linkedin.com/in/alexmoreau",
    github="https://github.com/alexmoreau",
)

LANGUAGES = """
## Langues

- Anglais : courant <!-- id=lang-en -->
- Espagnol : intermédiaire <!-- id=lang-es -->
"""

OFFER = OfferInput(
    title="Ingénieur data plateforme",
    company="Plume Énergie",
    description="Pipelines Airflow sur PostgreSQL pour le suivi de parcs solaires.",
)


def cv_text() -> str:
    fixture = (ROOT / "evals" / "fixtures" / "cv-verbeux.fr.md").read_text(encoding="utf-8")
    return fixture.rstrip() + "\n" + LANGUAGES


def proposal(texts: dict[str, str]) -> TailoredCv:
    """What the model proposed for the offer, once code checked it."""

    def item(
        item_id: str, text: str = "", proposed_rewrite: str = "", rejected_reason: str = ""
    ) -> ReviewedItem:
        return ReviewedItem(
            id=item_id,
            original=texts[item_id],
            text=text or texts[item_id],
            proposed_rewrite=proposed_rewrite,
            rejected_reason=rejected_reason,
        )

    def experience(item_id: str, bullets: list[ReviewedItem]) -> ReviewedExperience:
        return ReviewedExperience(**item(item_id).model_dump(), bullets=bullets)

    airflow = (
        "Migration sans interruption de service de 90 traitements nocturnes en scripts "
        "shell vers des DAG Airflow documentés et testés"
    )
    return TailoredCv(
        resume=item("resume-01"),
        experiences=[
            experience(
                "helianthe",
                [
                    item("helianthe-02", text=airflow, proposed_rewrite=airflow),
                    item("helianthe-01"),
                    item(
                        "helianthe-03",
                        proposed_rewrite="Temps de calcul de la facturation réduit de 60 % "
                        "grâce à une refonte des requêtes PostgreSQL",
                        rejected_reason="chiffre absent de la source : 60",
                    ),
                ],
            ),
            experience("transvia", [item("transvia-03"), item("transvia-01")]),
            experience("ardoise", [item("ardoise-03")]),
        ],
        projets=[item("project-01")],
        formation=[
            ReviewedFormation(**item("formation-01").model_dump()),
            ReviewedFormation(**item("formation-02").model_dump()),
        ],
        competences=[
            item(skill)
            for skill in (
                "skill-python",
                "skill-airflow",
                "skill-postgresql",
                "skill-gitlab",
                "skill-ansible",
                "skill-tests",
                "skill-django",
            )
        ],
        langues=[item("lang-en"), item("lang-es")],
        discarded=[
            DiscardedItem(
                id="fenouil",
                original=texts["fenouil"],
                reason="sites vitrines en PHP, loin d’une plateforme de données",
            ),
            DiscardedItem(
                id="helianthe-04",
                original=texts["helianthe-04"],
                reason="plus de place sur la page",
                by_code=True,
            ),
            DiscardedItem(id="skill-php", original=texts["skill-php"], reason="hors sujet"),
            DiscardedItem(id="skill-java", original=texts["skill-java"], reason="hors sujet"),
        ],
        complement_ids=["ardoise", "ardoise-03"],
    )


LETTER = {
    "accroche": (
        "Votre annonce pour un ingénieur data plateforme a retenu toute mon attention : "
        "fiabiliser les pipelines qui suivent des parcs solaires est exactement le travail "
        "que je mène depuis quatre ans."
    ),
    "adequation": (
        "Chez Hélianthe Énergie, j’ai conçu l’API Python qui collecte chaque jour les "
        "relevés de 3 000 compteurs solaires, puis migré 90 traitements nocturnes vers des "
        "DAG Airflow documentés et testés, sans interruption de service. J’ai aussi divisé "
        "par deux le temps de calcul de la facturation en reprenant les requêtes "
        "PostgreSQL et leurs index."
    ),
    "motivation": (
        "Votre plateforme sert directement la transition énergétique, et votre équipe "
        "data est encore petite : j’aimerais y apporter cette exigence de fiabilité, et "
        "en parler avec vous lors d’un entretien."
    ),
}


def letter_view() -> LetterView:
    slots = [("accroche", 60), ("adequation", 140), ("motivation", 100)]
    return LetterView(
        id=3,
        application_id=5,
        llm_call_id=31,
        created_at=AT,
        updated_at=AT,
        application_title=OFFER.title,
        company_name=OFFER.company,
        recipient="Plume Énergie, équipe data",
        slots=[
            SlotView(
                name=name,
                max_words=limit,
                text=LETTER[name],
                words=len(LETTER[name].split()),
                proposed=LETTER[name],
                rejected_reason="",
                unsourced_names=[],
            )
            for name, limit in slots
        ],
        cited_ids=["helianthe-01", "helianthe-02", "helianthe-03"],
        warnings=[],
        problems=[],
        max_pages=1,
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    text = cv_text()

    view = convert_draft(TextDraft(mode="text", text=text), "fr")
    document = CvDocument(**view.model_dump(), sha256="f" * 64, version=4, updated_at=AT)
    (OUT / "cv.json").write_text(document.model_dump_json(), encoding="utf-8")

    profile = parse_cv_markdown(text)
    tailored = proposal({item.id: item.text for item in profile.items})
    options = CvOptions(photo=False, panneau_competences=True, loisirs=False)
    choices = initial_choices(tailored, options)
    draft = DraftView(
        id=7,
        lang="fr",
        offer=OFFER,
        offer_id=2,
        application_id=5,
        llm_call_id=42,
        created_at=AT,
        updated_at=AT,
        **dict(draft_items(profile, tailored, choices)),
        options=options,
        option_blockers=OptionBlockers(
            photo="Ajoutez d'abord une photo dans votre identité.",
            panneau_competences=None,
            loisirs="Votre CV n'a pas de section Loisirs.",
        ),
        warnings=[],
        gone=0,
        max_pages=1,
    )
    (OUT / "draft.json").write_text(draft.model_dump_json(), encoding="utf-8")
    selection = draft_selection(
        profile, tailored, choices, template=load_manifest().name, lang="fr"
    )
    cv = render_cv(selection, ALEX)
    if cv.pages != 1:
        raise SystemExit(f"the adapted CV takes {cv.pages} pages, not one")
    (OUT / "cv.pdf").write_bytes(cv.pdf)

    letter = letter_view()
    rendered = render_letter(
        {slot.name: slot.text for slot in letter.slots},
        ALEX,
        offer_title=OFFER.title,
        recipient=letter.recipient,
        day=date(2026, 11, 12),
    )
    (OUT / "letter.pdf").write_bytes(rendered.pdf)
    (OUT / "letter.json").write_text(letter.model_dump_json(), encoding="utf-8")
    # The eval results are the committed, measured ones, never fictional.
    report = [task.model_dump(mode="json") for task in eval_report(ROOT / "evals" / "results")]
    (OUT / "evals.json").write_text(json.dumps(report), encoding="utf-8")
    print(f"written to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

"""Ask the model which parts of the CV serve an offer, then check its answer in code."""

import logging
from dataclasses import dataclass

from jobingo.db import Conn
from jobingo.domain.cv_document import CvLang
from jobingo.domain.cv_proposal import (
    TailoredCv,
    restore_ids,
    resume_source,
    review_proposal,
    short_ids,
)
from jobingo.domain.personal_data import find_personal_data
from jobingo.domain.profile import parse_cv_markdown
from jobingo.domain.style import StyleGuide
from jobingo.llm.client import LLMClient
from jobingo.llm.journal import Budget, run_task
from jobingo.llm.tasks.select_cv_content import (
    SELECT_CV_CONTENT_TASK,
    CvItemInput,
    SelectCvContentInput,
)
from jobingo.logs import event
from jobingo.render.cv import load_manifest
from jobingo.services.cv import load_cv
from jobingo.services.identity import redaction_values

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class OfferText:
    """The offer as the model reads it: text the user did not write."""

    title: str
    company: str
    description: str


class NothingToTailorError(Exception):
    """No CV, or nothing in it to choose from. The message is shown to the user."""


class PersonalDataInCvError(Exception):
    """The CV holds contact details, which must not reach the model. Shown to the user."""


def propose_cv(
    conn: Conn,
    client: LLMClient,
    budget: Budget,
    user_id: int,
    lang: CvLang,
    offer: OfferText,
    *,
    style: StyleGuide | None = None,
    hobbies: bool = True,
) -> tuple[TailoredCv, int]:
    """The CV adapted to `offer`, checked, with the id of the call that proposed it.

    `hobbies` is the user's choice for this CV: without it, the model is not shown
    them. Raises the errors above before any call, and `LLMCallError` or
    `LLMBudgetExceeded` from the call.
    """
    stored = load_cv(conn, user_id, lang)
    if stored is None:
        raise NothingToTailorError("Votre CV est vide : remplissez-le avant de l'adapter.")
    if find_personal_data(stored.content):
        raise PersonalDataInCvError(
            "Votre CV contient des coordonnées. Retirez-les dans « Mon CV » : elles "
            "vont dans l'identité, que le modèle ne lit jamais."
        )
    profile = parse_cv_markdown(stored.content)
    shown = [
        item
        for item in profile.items
        if item.kind != "resume" and (hobbies or item.kind != "hobby")
    ]
    if not shown:
        raise NothingToTailorError("Votre CV n'a rien à sélectionner pour cette offre.")

    style = style or StyleGuide()
    manifest = load_manifest()
    aliases = short_ids(shown)
    resume = resume_source(profile)
    payload = SelectCvContentInput(
        lang=lang,
        offer_title=offer.title,
        offer_company=offer.company,
        offer_description=offer.description,
        template_name=manifest.name,
        max_resume_chars=manifest.limits("resume").max_chars,
        max_experiences=manifest.limits("experiences").max_items,
        max_bullets_per_experience=manifest.limits("experiences").max_bullets_per_item,
        max_formation=manifest.limits("formation").max_items,
        max_competences=manifest.limits("competences").max_items,
        max_loisirs=manifest.limits("loisirs").max_items,
        max_projets=manifest.limits("projets").max_items,
        resume=resume.original if resume else "",
        items=[
            CvItemInput(
                id=aliases.get(item.id, item.id),
                kind=item.kind,
                text=item.text,
                tags=item.tags,
                parent_id=aliases.get(item.parent_id, item.parent_id) if item.parent_id else None,
            )
            for item in shown
        ],
        style_register=style.tone_register,
        style_examples=style.examples,
        style_forbidden=style.forbidden,
    )
    proposal, call_id = run_task(
        conn,
        client,
        budget,
        user_id,
        SELECT_CV_CONTENT_TASK,
        payload,
        redaction_values=redaction_values(conn, user_id),
    )
    tailored = review_proposal(restore_ids(proposal, aliases), profile, manifest, style)
    kept = tailored.kept_items()
    event(
        log,
        "cv.proposed",
        user_id=user_id,
        llm_call_id=call_id,
        kept=len(kept),
        rewritten=sum(item.rewritten for item in kept),
        refused_rewrites=sum(bool(item.rejected_reason) for item in kept),
        discarded=len(tailored.discarded),
        warnings=len(tailored.warnings),
    )
    return tailored, call_id

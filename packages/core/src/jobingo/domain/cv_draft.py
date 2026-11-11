"""A CV adapted to one offer: the model's proposal as code checked it, kept unchanged as
the trail, and the user's choices on top of it.

The user disposes. Their choices may keep what the model left out, drop what it kept,
adopt a rewrite that code refused, or write their own words: the checks on rewrites
frame the model, not the person whose CV it is.
"""

from collections.abc import Collection
from datetime import datetime

from pydantic import BaseModel, Field

from jobingo.domain.chronology import sort_reverse_chronological
from jobingo.domain.cv_proposal import ReviewedItem, TailoredCv, resume_source
from jobingo.domain.cv_selection import (
    CvOptions,
    CvSelection,
    OptionBlockers,
    SelectedExperience,
    SelectedFormation,
    SelectedItem,
)
from jobingo.domain.profile import Profile, ProfileItem

MAX_TEXT = 1000


class OfferInput(BaseModel):
    """An offer pasted by the user, until offers have their own screen."""

    title: str = Field(min_length=1, max_length=300)
    company: str = Field(default="", max_length=300)
    description: str = Field(min_length=1, max_length=20_000)


class DraftChoices(BaseModel):
    """What the user settled: the ids on the page, their own texts, the options."""

    kept_ids: list[str]
    # Text per id, when it differs from the CV: an accepted rewrite or the user's words.
    texts: dict[str, str]
    options: CvOptions


def initial_choices(tailored: TailoredCv, options: CvOptions) -> DraftChoices:
    kept = tailored.kept_items()
    return DraftChoices(
        kept_ids=[item.id for item in kept],
        texts={item.id: item.text for item in kept if item.rewritten},
        options=options,
    )


def cleaned_choices(choices: DraftChoices, profile: Profile) -> DraftChoices:
    """Only ids the CV has, and texts that are not blank or the CV's own."""
    sources = _sources(profile)
    texts = {
        item_id: text.strip()[:MAX_TEXT]
        for item_id, text in choices.texts.items()
        if item_id in sources and text.strip() and text.strip() != sources[item_id].strip()
    }
    kept = [item_id for item_id in dict.fromkeys(choices.kept_ids) if item_id in sources]
    return DraftChoices(kept_ids=kept, texts=texts, options=choices.options)


def _sources(profile: Profile) -> dict[str, str]:
    """The CV's text per id; the summary is all its lines, under the first id."""
    sources = {item.id: item.text for item in profile.items if item.kind != "resume"}
    resume = resume_source(profile)
    if resume is not None:
        sources[resume.id] = resume.original
    return sources


def _proposal_rank(tailored: TailoredCv) -> dict[str, int]:
    return {item.id: rank for rank, item in enumerate(tailored.kept_items())}


def draft_selection(
    profile: Profile,
    tailored: TailoredCv,
    choices: DraftChoices,
    *,
    template: str,
    lang: str,
) -> CvSelection:
    """The render-ready selection. Experiences and education go by date, most recent
    first; within a section, what the model chose keeps its order, then what the user
    added, in CV order."""
    kept = set(choices.kept_ids)
    rank = _proposal_rank(tailored)

    def ordered(items: list[ProfileItem]) -> list[ProfileItem]:
        chosen = [item for item in items if item.id in kept]
        return sorted(chosen, key=lambda item: rank.get(item.id, len(rank)))

    def text_of(item_id: str, original: str) -> str:
        return choices.texts.get(item_id, original)

    def of_kind(kind: str) -> list[ProfileItem]:
        return [item for item in profile.items if item.kind == kind]

    experiences = sort_reverse_chronological(ordered(of_kind("experience")), lambda e: e.text)
    formation = sort_reverse_chronological(ordered(of_kind("formation")), lambda f: f.text)
    resume = resume_source(profile)
    return CvSelection(
        template=template,
        lang=lang,
        resume=(
            SelectedItem(id=resume.id, text=text_of(resume.id, resume.original))
            if resume and resume.id in kept
            else None
        ),
        experiences=[
            SelectedExperience(
                id=experience.id,
                text=text_of(experience.id, experience.text),
                bullets=[
                    SelectedItem(id=bullet.id, text=text_of(bullet.id, bullet.text))
                    for bullet in ordered(
                        [b for b in of_kind("bullet") if b.parent_id == experience.id]
                    )
                ],
            )
            for experience in experiences
        ],
        projets=[
            SelectedItem(id=p.id, text=text_of(p.id, p.text)) for p in ordered(of_kind("project"))
        ],
        formation=[
            SelectedFormation(id=f.id, text=text_of(f.id, f.text), heading=f.heading)
            for f in formation
        ],
        competences=[
            SelectedItem(id=s.id, text=text_of(s.id, s.text)) for s in ordered(of_kind("skill"))
        ],
        loisirs=[
            SelectedItem(id=h.id, text=text_of(h.id, h.text)) for h in ordered(of_kind("hobby"))
        ],
        options=choices.options,
    )


# --- The diff screen ---------------------------------------------------------------


class DraftItem(BaseModel):
    id: str
    original: str  # the CV's text
    text: str  # the text on the page now
    kept: bool  # on the page now
    # What the model did with this item.
    proposed: bool  # the model kept it
    proposed_rewrite: str  # empty: no rewrite proposed
    rejected_reason: str  # why code refused the rewrite; empty when accepted or none
    unsourced_names: list[str]  # proper nouns the accepted rewrite added, to check
    discard_reason: str  # the model's motive for leaving it out, if it gave one


class DraftExperience(DraftItem):
    bullets: list[DraftItem]


class DraftFormation(DraftItem):
    heading: bool


class DraftSummary(BaseModel):
    id: int
    offer_id: int | None
    # The application it was made for; None for a draft made before CVs belonged to
    # applications, with no live application for its offer.
    application_id: int | None
    offer_title: str
    offer_company: str
    llm_call_id: int | None
    created_at: datetime
    updated_at: datetime


class DraftSections(BaseModel):
    """The whole CV, section by section, as the diff screen shows it."""

    resume: DraftItem | None
    experiences: list[DraftExperience]
    projets: list[DraftItem]
    formation: list[DraftFormation]
    competences: list[DraftItem]
    loisirs: list[DraftItem]


class DraftView(BaseModel):
    id: int
    lang: str
    offer: OfferInput
    # The stored offer it was adapted to; None for a spontaneous application.
    offer_id: int | None
    application_id: int | None
    llm_call_id: int | None
    created_at: datetime
    updated_at: datetime
    resume: DraftItem | None
    experiences: list[DraftExperience]
    projets: list[DraftItem]
    formation: list[DraftFormation]
    competences: list[DraftItem]
    loisirs: list[DraftItem]
    options: CvOptions
    option_blockers: OptionBlockers
    # Ids the model named that the CV does not have, or put in the wrong place.
    warnings: list[str]
    # Items the proposal kept that the CV no longer has, since it was edited.
    gone: int
    max_pages: int


def _reviewed_index(tailored: TailoredCv) -> dict[str, ReviewedItem]:
    return {item.id: item for item in tailored.kept_items()}


def draft_items(profile: Profile, tailored: TailoredCv, choices: DraftChoices) -> DraftSections:
    """The whole CV, in its own order, each item with the model's proposal and the
    user's current choice."""
    reviewed = _reviewed_index(tailored)
    discarded = {d.id: d.reason for d in tailored.discarded}
    kept = set(choices.kept_ids)

    def item(item_id: str, original: str) -> DraftItem:
        proposal = reviewed.get(item_id)
        return DraftItem(
            id=item_id,
            original=original,
            text=choices.texts.get(item_id, original),
            kept=item_id in kept,
            proposed=proposal is not None,
            proposed_rewrite=proposal.proposed_rewrite if proposal else "",
            rejected_reason=proposal.rejected_reason if proposal else "",
            unsourced_names=proposal.unsourced_names if proposal else [],
            discard_reason=discarded.get(item_id, ""),
        )

    def of_kind(kind: str) -> list[ProfileItem]:
        return [source for source in profile.items if source.kind == kind]

    resume = resume_source(profile)
    experiences: list[DraftExperience] = []
    for source in of_kind("experience"):
        experiences.append(
            DraftExperience(
                **item(source.id, source.text).model_dump(),
                bullets=[
                    item(bullet.id, bullet.text)
                    for bullet in of_kind("bullet")
                    if bullet.parent_id == source.id
                ],
            )
        )
    return DraftSections(
        resume=item(resume.id, resume.original) if resume else None,
        experiences=experiences,
        projets=[item(p.id, p.text) for p in of_kind("project")],
        formation=[
            DraftFormation(**item(f.id, f.text).model_dump(), heading=f.heading)
            for f in of_kind("formation")
        ],
        competences=[item(s.id, s.text) for s in of_kind("skill")],
        loisirs=[item(h.id, h.text) for h in of_kind("hobby")],
    )


def gone_items(profile: Profile, tailored: TailoredCv) -> int:
    known: Collection[str] = _sources(profile)
    return sum(item.id not in known for item in tailored.kept_items())

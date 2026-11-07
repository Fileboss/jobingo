"""The model's proposal for one offer, and what code makes of it.

The model selects from the user's exhaustive CV and may lightly rewrite. Code then
checks everything: an id must exist in the right section, the template's limits hold,
and a rewrite that is too long, adds a number or uses a forbidden turn of phrase is
refused, the original text kept. Nothing here can fail: a bad proposal degrades to the
user's own words, and the review keeps the trail of what was proposed and refused.

This lives in `domain` because `llm` binds `CvProposalSchema` as the task's answer and
`domain` may not import `llm`.
"""

from typing import Any, Literal

from pydantic import BaseModel, model_validator

from jobingo.domain.chronology import sort_reverse_chronological
from jobingo.domain.cv_selection import (
    CvOptions,
    CvSelection,
    SelectedExperience,
    SelectedFormation,
    SelectedItem,
)
from jobingo.domain.cv_template import CvManifest, CvSection
from jobingo.domain.profile import Profile, ProfileItem
from jobingo.domain.style import StyleGuide, forbidden_hits
from jobingo.domain.text_checks import numbers_in, unsourced_proper_nouns

MAX_REWRITE_RATIO = 1.2

type ProposalSection = Literal["experiences", "bullets", "formation", "competences", "loisirs"]
PROPOSAL_SECTIONS: tuple[ProposalSection, ...] = (
    "experiences",
    "bullets",
    "formation",
    "competences",
    "loisirs",
)
_SECTION_OF_KIND: dict[str, CvSection] = {
    "experience": "experiences",
    "bullet": "experiences",
    "formation": "formation",
    "skill": "competences",
    "hobby": "loisirs",
}


class ProposedItem(BaseModel):
    id: str
    rewrite: str = ""  # empty keeps the original wording


class ProposedDiscard(BaseModel):
    id: str
    reason: str


class ProposedRewrite(BaseModel):
    id: str
    text: str


class CvProposalSchema(BaseModel):
    """What the API is asked to answer: each section a list of ids, and the rare
    rewrites apart. Repeating `{"id": …, "rewrite": ""}` for every kept item made most
    of the output tokens padding."""

    resume: str = ""
    experiences: list[str] = []
    bullets: list[str] = []
    formation: list[str] = []
    competences: list[str] = []
    loisirs: list[str] = []
    rewrites: list[ProposedRewrite] = []
    discarded: list[ProposedDiscard] = []


class CvProposal(BaseModel):
    """The proposal with each rewrite folded back onto its item. Bullets come as one
    flat list: their experience is known from the CV, so nesting would only give the
    model a second way to get it wrong."""

    resume: str = ""
    experiences: list[ProposedItem] = []
    bullets: list[ProposedItem] = []
    formation: list[ProposedItem] = []
    competences: list[ProposedItem] = []
    loisirs: list[ProposedItem] = []
    discarded: list[ProposedDiscard] = []

    @model_validator(mode="before")
    @classmethod
    def _fold_rewrites(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        raw: dict[str, Any] = dict(data)  # pyright: ignore[reportUnknownArgumentType]
        texts: dict[str, str] = {}
        rewrites: object = raw.pop("rewrites", [])
        for rewrite in rewrites if isinstance(rewrites, list) else []:  # pyright: ignore[reportUnknownVariableType]
            if isinstance(rewrite, dict) and isinstance(rewrite.get("id"), str):  # pyright: ignore[reportUnknownMemberType]
                texts[rewrite["id"]] = str(rewrite.get("text", ""))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        for section in PROPOSAL_SECTIONS:
            items: object = raw.get(section)
            if isinstance(items, list):
                raw[section] = [
                    {"id": item, "rewrite": texts.get(item, "")} if isinstance(item, str) else item
                    for item in items  # pyright: ignore[reportUnknownVariableType]
                ]
        return raw


# --- Short ids --------------------------------------------------------------

_ALIAS_PREFIX = {"experience": "E", "formation": "F", "skill": "C", "hobby": "L", "bullet": "P"}


def short_ids(items: list[ProfileItem]) -> dict[str, str]:
    """A short alias for every id the model is shown: `E2` for the second experience,
    `E2.3` for its third bullet, `F1`, `C4`, `L1`. The CV's own ids cost several tokens
    each, in the prompt and again in the answer, and the alias also states the parent."""
    aliases: dict[str, str] = {}
    counters: dict[str, int] = {}
    for item in items:
        if item.kind == "bullet" and item.parent_id in aliases:
            parent = aliases[item.parent_id]
            counters[parent] = counters.get(parent, 0) + 1
            aliases[item.id] = f"{parent}.{counters[parent]}"
        elif item.kind in _ALIAS_PREFIX:
            prefix = _ALIAS_PREFIX[item.kind]
            counters[prefix] = counters.get(prefix, 0) + 1
            aliases[item.id] = f"{prefix}{counters[prefix]}"
    return aliases


def restore_ids(proposal: CvProposal, aliases: dict[str, str]) -> CvProposal:
    """The proposal with the CV's own ids back. An id that is no alias is left as is,
    and reported as unknown later."""
    real = {alias: item_id for item_id, alias in aliases.items()}

    def back(item_id: str) -> str:
        return real.get(item_id.strip(), item_id)

    update: dict[str, Any] = {
        section: [
            item.model_copy(update={"id": back(item.id)}) for item in getattr(proposal, section)
        ]
        for section in PROPOSAL_SECTIONS
    }
    update["discarded"] = [d.model_copy(update={"id": back(d.id)}) for d in proposal.discarded]
    return proposal.model_copy(update=update)


# --- Checks -----------------------------------------------------------------


def validate_rewrite(
    original: str, rewrite: str, style: StyleGuide, max_chars: int | None = None
) -> str | None:
    """Why a rewrite must be refused, in French for the review screen, or None.

    The remedy is always the same, keeping the original text, so this returns a
    reason rather than raising.
    """
    rewrite = rewrite.strip()
    if not rewrite or rewrite == original.strip():
        return None
    if len(rewrite) > MAX_REWRITE_RATIO * len(original):
        percent = round(100 * len(rewrite) / len(original)) if original else 0
        return (
            f"reformulation trop longue ({percent} % de l'original, "
            f"{round(100 * MAX_REWRITE_RATIO)} % au maximum)"
        )
    if max_chars is not None and len(rewrite) > max_chars:
        return f"reformulation trop longue pour le gabarit ({max_chars} caractères au maximum)"
    source_numbers = numbers_in(original)
    invented = [number for number in numbers_in(rewrite) if number not in source_numbers]
    if invented:
        return f"chiffre absent de la source : {invented[0]}"
    hits = forbidden_hits(rewrite, style.forbidden)
    if hits:
        return f"tournure interdite : {hits[0]}"
    return None


# --- The reviewed proposal ----------------------------------------------------


class ReviewedItem(BaseModel):
    """One item as it will be shown, with the trail of what the model proposed."""

    id: str
    original: str
    text: str
    proposed_rewrite: str = ""
    rejected_reason: str = ""
    # Proper nouns an accepted rewrite added, for the user to check.
    unsourced_names: list[str] = []

    @property
    def rewritten(self) -> bool:
        return self.text.strip() != self.original.strip()


class ReviewedFormation(ReviewedItem):
    heading: bool = False


class ReviewedExperience(ReviewedItem):
    bullets: list[ReviewedItem] = []


class DiscardedItem(BaseModel):
    id: str
    original: str = ""
    reason: str


class TailoredCv(BaseModel):
    """The proposal once checked: what goes on the page for this offer, and why."""

    resume: ReviewedItem | None = None
    experiences: list[ReviewedExperience] = []
    formation: list[ReviewedFormation] = []
    competences: list[ReviewedItem] = []
    loisirs: list[ReviewedItem] = []
    discarded: list[DiscardedItem] = []
    # Ids that do not exist, sit in the wrong section or repeat: dropped, and said.
    warnings: list[str] = []

    def kept_items(self) -> list[ReviewedItem]:
        items: list[ReviewedItem] = []
        if self.resume is not None:
            items.append(self.resume)
        for experience in self.experiences:
            items.append(experience)
            items.extend(experience.bullets)
        items.extend(self.formation)
        items.extend(self.competences)
        items.extend(self.loisirs)
        return items

    def selection(self, *, template: str, lang: str, options: CvOptions) -> CvSelection:
        """The render-ready selection of the texts as they stand."""

        def plain(item: ReviewedItem) -> SelectedItem:
            return SelectedItem(id=item.id, text=item.text)

        return CvSelection(
            template=template,
            lang=lang,
            resume=plain(self.resume) if self.resume else None,
            experiences=[
                SelectedExperience(
                    id=e.id, text=e.text, bullets=[plain(bullet) for bullet in e.bullets]
                )
                for e in self.experiences
            ],
            formation=[
                SelectedFormation(id=f.id, text=f.text, heading=f.heading) for f in self.formation
            ],
            competences=[plain(item) for item in self.competences],
            loisirs=[plain(item) for item in self.loisirs],
            options=options,
        )


def resume_source(profile: Profile) -> ReviewedItem | None:
    """The summary is every line of its section, under the first line's id."""
    lines = [item for item in profile.items if item.kind == "resume"]
    if not lines:
        return None
    text = " ".join(line.text for line in lines)
    return ReviewedItem(id=lines[0].id, original=text, text=text)


def _reviewed(item: ProfileItem, rewrite: str, style: StyleGuide) -> ReviewedItem:
    reason = validate_rewrite(item.text, rewrite, style)
    text = rewrite.strip() if rewrite.strip() and not reason else item.text
    return ReviewedItem(
        id=item.id,
        original=item.text,
        text=text,
        proposed_rewrite=rewrite.strip(),
        rejected_reason=reason or "",
        unsourced_names=unsourced_proper_nouns(text, item.text),
    )


def _cut[T: ReviewedItem](
    items: list[T], max_items: int | None, label: str, discarded: list[DiscardedItem]
) -> list[T]:
    if max_items is None or len(items) <= max_items:
        return items
    for extra in items[max_items:]:
        discarded.append(
            DiscardedItem(
                id=extra.id,
                original=extra.original,
                reason=f"limite du gabarit : {max_items} {label} au maximum",
            )
        )
    return items[:max_items]


def review_proposal(
    proposal: CvProposal, profile: Profile, manifest: CvManifest, style: StyleGuide
) -> TailoredCv:
    index: dict[str, ProfileItem] = {}
    for item in profile.items:
        index.setdefault(item.id, item)
    warnings: list[str] = []
    discarded = [
        DiscardedItem(id=d.id, original=index[d.id].text if d.id in index else "", reason=d.reason)
        for d in proposal.discarded
    ]

    seen: set[str] = set()
    chosen: dict[str, list[ReviewedItem]] = {}
    for section in PROPOSAL_SECTIONS:
        expected: CvSection = "experiences" if section == "bullets" else section
        for proposed in getattr(proposal, section):
            assert isinstance(proposed, ProposedItem)
            item = index.get(proposed.id)
            if item is None:
                warnings.append(f"identifiant inconnu, ignoré : '{proposed.id}'")
            elif _SECTION_OF_KIND.get(item.kind) != expected:
                warnings.append(f"identifiant '{proposed.id}' dans la mauvaise section, ignoré")
            elif proposed.id in seen:
                warnings.append(f"identifiant '{proposed.id}' proposé deux fois, ignoré")
            else:
                seen.add(proposed.id)
                chosen.setdefault(item.kind, []).append(_reviewed(item, proposed.rewrite, style))

    limits = manifest.limits("experiences")
    experiences = _cut(chosen.get("experience", []), limits.max_items, "expériences", discarded)
    kept = {experience.id for experience in experiences}
    bullets: dict[str, list[ReviewedItem]] = {}
    for bullet in chosen.get("bullet", []):
        parent = index[bullet.id].parent_id
        if parent is None or parent not in kept:
            warnings.append(f"puce '{bullet.id}' d'une expérience non retenue, ignorée")
            continue
        bullets.setdefault(parent, []).append(bullet)
    built = [
        ReviewedExperience(
            **experience.model_dump(),
            bullets=_cut(
                bullets.get(experience.id, []),
                limits.max_bullets_per_item,
                "puces par expérience",
                discarded,
            ),
        )
        for experience in experiences
    ]
    formation = [
        ReviewedFormation(**item.model_dump(), heading=index[item.id].heading)
        for item in _cut(
            chosen.get("formation", []),
            manifest.limits("formation").max_items,
            "éléments de formation",
            discarded,
        )
    ]

    return TailoredCv(
        resume=_review_resume(proposal.resume, profile, manifest, style, warnings),
        # The model picks these two sections; the code orders them, most recent first.
        experiences=sort_reverse_chronological(built, lambda e: e.original),
        formation=sort_reverse_chronological(formation, lambda f: f.original),
        competences=_cut(
            chosen.get("skill", []),
            manifest.limits("competences").max_items,
            "compétences",
            discarded,
        ),
        loisirs=_cut(
            chosen.get("hobby", []), manifest.limits("loisirs").max_items, "loisirs", discarded
        ),
        discarded=discarded,
        warnings=warnings,
    )


def _review_resume(
    rewrite: str, profile: Profile, manifest: CvManifest, style: StyleGuide, warnings: list[str]
) -> ReviewedItem | None:
    source = resume_source(profile)
    if source is None:
        if rewrite.strip():
            warnings.append("résumé proposé alors que le CV n'en a pas, ignoré")
        return None
    max_chars = manifest.limits("resume").max_chars
    reason = validate_rewrite(source.original, rewrite, style, max_chars=max_chars)
    text = rewrite.strip() if rewrite.strip() and not reason else source.original
    return source.model_copy(
        update={
            "text": text,
            "proposed_rewrite": rewrite.strip(),
            "rejected_reason": reason or "",
            "unsourced_names": unsourced_proper_nouns(text, source.original),
        }
    )

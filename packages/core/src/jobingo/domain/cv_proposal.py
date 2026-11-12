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

type ProposalSection = Literal[
    "experiences", "bullets", "projets", "formation", "competences", "loisirs"
]
PROPOSAL_SECTIONS: tuple[ProposalSection, ...] = (
    "experiences",
    "bullets",
    "projets",
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
    "project": "projets",
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


class CvRankingSchema(BaseModel):
    """What the API is asked to answer: the main column's elements in two rankings, what
    serves the offer and what only completes the page, each most useful first, and the
    side sections as lists. Rewrites come apart, since repeating `{"id": …, "rewrite":
    ""}` for every element made most of the output tokens padding."""

    resume: str = ""
    sert_l_offre: list[str] = []
    complement: list[str] = []
    competences: list[str] = []
    loisirs: list[str] = []
    rewrites: list[ProposedRewrite] = []
    discarded: list[ProposedDiscard] = []


RANKING_SECTIONS = ("sert_l_offre", "complement", "competences", "loisirs")


def _fold_rewrites(data: Any, sections: tuple[str, ...]) -> Any:
    """Each rewrite folded back onto its item, ids becoming `ProposedItem`s."""
    if not isinstance(data, dict):
        return data
    raw: dict[str, Any] = dict(data)  # pyright: ignore[reportUnknownArgumentType]
    texts: dict[str, str] = {}
    rewrites: object = raw.pop("rewrites", [])
    for rewrite in rewrites if isinstance(rewrites, list) else []:  # pyright: ignore[reportUnknownVariableType]
        if isinstance(rewrite, dict) and isinstance(rewrite.get("id"), str):  # pyright: ignore[reportUnknownMemberType]
            texts[rewrite["id"]] = str(rewrite.get("text", ""))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    for section in sections:
        items: object = raw.get(section)
        if isinstance(items, list):
            raw[section] = [
                {"id": item, "rewrite": texts.get(item, "")} if isinstance(item, str) else item
                for item in items  # pyright: ignore[reportUnknownVariableType]
            ]
    return raw


class CvRanking(BaseModel):
    """The model's answer with each rewrite folded back onto its item."""

    resume: str = ""
    sert_l_offre: list[ProposedItem] = []
    complement: list[ProposedItem] = []
    competences: list[ProposedItem] = []
    loisirs: list[ProposedItem] = []
    discarded: list[ProposedDiscard] = []

    @model_validator(mode="before")
    @classmethod
    def _fold(cls, data: Any) -> Any:
        return _fold_rewrites(data, RANKING_SECTIONS)

    @property
    def classement(self) -> list[ProposedItem]:
        """The order code takes elements in: what serves the offer, then what completes
        the page."""
        return [*self.sert_l_offre, *self.complement]


class CvProposal(BaseModel):
    """What goes on the page, by section: the first elements of the model's ranking
    (`proposal_at`). Bullets come as one flat list: their experience is known from the
    CV. `beyond_page` is the rest of the ranking, left out by code for lack of room."""

    resume: str = ""
    experiences: list[ProposedItem] = []
    bullets: list[ProposedItem] = []
    projets: list[ProposedItem] = []
    formation: list[ProposedItem] = []
    competences: list[ProposedItem] = []
    loisirs: list[ProposedItem] = []
    discarded: list[ProposedDiscard] = []
    beyond_page: list[ProposedDiscard] = []
    # Taken from the model's `complement`: what completes the page, not serving the offer.
    complement_ids: list[str] = []

    @model_validator(mode="before")
    @classmethod
    def _fold(cls, data: Any) -> Any:
        return _fold_rewrites(data, PROPOSAL_SECTIONS)


_KIND_SECTION: dict[str, ProposalSection] = {
    "experience": "experiences",
    "bullet": "bullets",
    "project": "projets",
    "formation": "formation",
    "skill": "competences",
    "hobby": "loisirs",
}


def proposal_at(
    ranking: CvRanking, n: int, profile: Profile, *, side: int | None = None
) -> CvProposal:
    """The first `n` ranked elements of the main column as a proposal by section, and the
    first `side` of the side panel's (skills, then hobbies; all by default), the rest
    left out for lack of room. A bullet ranked before its experience brings it along: it
    cannot stand alone, and the model ranked it. Unknown ids go through, for the review
    to report."""
    index = {item.id: item for item in profile.items}
    sections: dict[str, list[ProposedItem]] = {section: [] for section in PROPOSAL_SECTIONS}
    taken: set[str] = set()

    def take(item: ProposedItem) -> None:
        if item.id in taken:
            return
        taken.add(item.id)
        source = index.get(item.id)
        section = _KIND_SECTION.get(source.kind, "experiences") if source else "experiences"
        sections[section].append(item)

    for item in ranking.classement[:n]:
        source = index.get(item.id)
        if source is not None and source.kind == "bullet" and source.parent_id:
            if source.parent_id not in taken:
                take(ProposedItem(id=source.parent_id))
        take(item)
    beyond = [
        ProposedDiscard(id=item.id, reason=f"faute de place : {rank}e du classement du modèle")
        for rank, item in enumerate(ranking.classement[n:], start=n + 1)
        if item.id not in taken
    ]
    panel = [*ranking.competences, *ranking.loisirs]
    kept_side = panel if side is None else panel[:side]
    beyond += [
        ProposedDiscard(id=item.id, reason="faute de place dans le panneau latéral")
        for item in panel[len(kept_side) :]
    ]
    kept_ids = {item.id for item in kept_side}
    return CvProposal(
        resume=ranking.resume,
        experiences=sections["experiences"],
        bullets=sections["bullets"],
        projets=sections["projets"],
        formation=sections["formation"],
        competences=[item for item in ranking.competences if item.id in kept_ids],
        loisirs=[item for item in ranking.loisirs if item.id in kept_ids],
        discarded=ranking.discarded,
        beyond_page=beyond,
        complement_ids=[item.id for item in ranking.complement if item.id in taken],
    )


# --- Short ids --------------------------------------------------------------

_ALIAS_PREFIX = {
    "experience": "E",
    "formation": "F",
    "skill": "C",
    "hobby": "L",
    "project": "R",
    "bullet": "P",
}


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


def restore_ids(ranking: CvRanking, aliases: dict[str, str]) -> CvRanking:
    """The ranking with the CV's own ids back. An id that is no alias is left as is,
    and reported as unknown later."""
    real = {alias: item_id for item_id, alias in aliases.items()}

    def back(item_id: str) -> str:
        return real.get(item_id.strip(), item_id)

    update: dict[str, Any] = {
        section: [
            item.model_copy(update={"id": back(item.id)}) for item in getattr(ranking, section)
        ]
        for section in RANKING_SECTIONS
    }
    update["discarded"] = [d.model_copy(update={"id": back(d.id)}) for d in ranking.discarded]
    return ranking.model_copy(update=update)


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
    # Left out by code (a template limit, no room on the page), not by the model.
    by_code: bool = False


class TailoredCv(BaseModel):
    """The proposal once checked: what goes on the page for this offer, and why."""

    resume: ReviewedItem | None = None
    experiences: list[ReviewedExperience] = []
    projets: list[ReviewedItem] = []
    formation: list[ReviewedFormation] = []
    competences: list[ReviewedItem] = []
    # Every language of the CV: the model does not see them, code always keeps them.
    langues: list[ReviewedItem] = []
    loisirs: list[ReviewedItem] = []
    discarded: list[DiscardedItem] = []
    # Ids that do not exist, sit in the wrong section or repeat: dropped, and said.
    warnings: list[str] = []
    # On the page to complete it, the model saying they do not serve the offer.
    complement_ids: list[str] = []

    def kept_items(self) -> list[ReviewedItem]:
        items: list[ReviewedItem] = []
        if self.resume is not None:
            items.append(self.resume)
        for experience in self.experiences:
            items.append(experience)
            items.extend(experience.bullets)
        items.extend(self.projets)
        items.extend(self.formation)
        items.extend(self.competences)
        items.extend(self.langues)
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
            projets=[plain(item) for item in self.projets],
            formation=[
                SelectedFormation(id=f.id, text=f.text, heading=f.heading) for f in self.formation
            ],
            competences=[plain(item) for item in self.competences],
            langues=[plain(item) for item in self.langues],
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


def with_final_period_of(original: str, rewrite: str) -> str:
    """`rewrite` ending with a period exactly when `original` does: a rewrite keeps the
    CV's own punctuation, so that the bullets of one list agree. Other final marks
    (`?`, `:`, an ellipsis) are left as they are."""
    original, rewrite = original.rstrip(), rewrite.rstrip()
    if not original or not rewrite:
        return rewrite
    if original.endswith(".") and not original.endswith(".."):
        return rewrite if rewrite[-1] in ".!?…:;" else rewrite + "."
    if original[-1].isalnum() or original[-1] in ")»%":
        if rewrite.endswith(".") and not rewrite.endswith(("..", "etc.")):
            return rewrite[:-1].rstrip()
    return rewrite


def _reviewed(item: ProfileItem, rewrite: str, style: StyleGuide) -> ReviewedItem:
    reason = validate_rewrite(item.text, rewrite, style)
    rewrite = with_final_period_of(item.text, rewrite.strip())
    text = rewrite if rewrite and not reason else item.text
    return ReviewedItem(
        id=item.id,
        original=item.text,
        text=text,
        proposed_rewrite=rewrite,
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
                by_code=True,
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
    ] + [
        DiscardedItem(
            id=d.id,
            original=index[d.id].text if d.id in index else "",
            reason=d.reason,
            by_code=True,
        )
        for d in proposal.beyond_page
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
        projets=_cut(
            chosen.get("project", []),
            manifest.limits("projets").max_items,
            "projets personnels",
            discarded,
        ),
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
        langues=[
            ReviewedItem(id=item.id, original=item.text, text=item.text)
            for item in profile.items
            if item.kind == "language"
        ],
        discarded=discarded,
        warnings=warnings,
        complement_ids=proposal.complement_ids,
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
    rewrite = with_final_period_of(source.original, rewrite.strip())
    text = rewrite if rewrite and not reason else source.original
    return source.model_copy(
        update={
            "text": text,
            "proposed_rewrite": rewrite,
            "rejected_reason": reason or "",
            "unsourced_names": unsourced_proper_nouns(text, source.original),
        }
    )

"""What goes on the page: the user's choices, and the CV as the page sees it.

Choices are stored as the ids left out, so a new CV item is on the page by default and
a removed one is forgotten. Nothing here carries identity: the renderer receives it apart.
"""

from collections.abc import Collection

from pydantic import BaseModel

from jobingo.domain.cv_fields import split_title
from jobingo.domain.cv_template import CvManifest
from jobingo.domain.profile import Profile, ProfileItem


class CvOptions(BaseModel):
    photo: bool
    panneau_competences: bool
    loisirs: bool

    def clamped_to(self, blockers: "OptionBlockers") -> "CvOptions":
        return CvOptions(
            photo=self.photo and blockers.photo is None,
            panneau_competences=(self.panneau_competences and blockers.panneau_competences is None),
            loisirs=self.loisirs and blockers.loisirs is None,
        )

    def kept_where_blocked(self, previous: "CvOptions", blockers: "OptionBlockers") -> "CvOptions":
        """These options, except that a blocked one keeps its previous value: the screen
        shows it off, which is no choice of the user's, and it may become available."""
        return CvOptions(
            photo=previous.photo if blockers.photo else self.photo,
            panneau_competences=(
                previous.panneau_competences
                if blockers.panneau_competences
                else self.panneau_competences
            ),
            loisirs=previous.loisirs if blockers.loisirs else self.loisirs,
        )


# Everything the CV holds is on the page, hobbies included. The photo is the one the
# user opts into.
DEFAULT_OPTIONS = CvOptions(photo=False, panneau_competences=True, loisirs=True)


class OptionBlockers(BaseModel):
    """Why each option cannot be on, in French for the screen. None when it can."""

    photo: str | None
    panneau_competences: str | None
    loisirs: str | None

    def first_blocking(self, options: CvOptions) -> str | None:
        blocked = (
            (options.photo, self.photo),
            (options.panneau_competences, self.panneau_competences),
            (options.loisirs, self.loisirs),
        )
        return next((reason for wanted, reason in blocked if wanted and reason), None)


def option_blockers(manifest: CvManifest, *, has_photo: bool, has_hobbies: bool) -> OptionBlockers:
    undeclared = "Ce gabarit ne propose pas cette option."
    photo = None if has_photo else "Ajoutez d'abord une photo dans votre identité."
    loisirs = None if has_hobbies else "Votre CV n'a pas de section Loisirs."
    return OptionBlockers(
        photo=photo if "photo" in manifest.options else undeclared,
        panneau_competences=None if "panneau_competences" in manifest.options else undeclared,
        loisirs=loisirs if "loisirs" in manifest.options else undeclared,
    )


class SelectionChoice(BaseModel):
    excluded_ids: list[str]
    options: CvOptions


class PageItem(BaseModel):
    id: str
    text: str
    selected: bool


class PageExperience(PageItem):
    dates: str  # `text` is the title without them. Empty when the title has no dates field.
    bullets: list[PageItem]


class PageFormation(PageItem):
    heading: bool  # a `###` line. Ticked on its own, like the lines under it.


class CvPage(BaseModel):
    """The CV with what is on the page, for the selection screen."""

    resume: PageItem | None  # one tick for the whole summary, on its first line's id
    experiences: list[PageExperience]
    formation: list[PageFormation]
    competences: list[PageItem]
    loisirs: list[PageItem]
    excluded_ids: list[str]
    options: CvOptions  # as they apply: an option that is blocked is off
    option_blockers: OptionBlockers
    max_pages: int


class SelectedItem(BaseModel):
    id: str
    text: str


class SelectedFormation(SelectedItem):
    heading: bool


class SelectedExperience(SelectedItem):
    bullets: list[SelectedItem]


class CvSelection(BaseModel):
    """The render-ready selection."""

    template: str
    lang: str
    resume: SelectedItem | None
    experiences: list[SelectedExperience]
    formation: list[SelectedFormation]
    competences: list[SelectedItem]
    loisirs: list[SelectedItem]
    options: CvOptions

    def kept_items(self) -> list[SelectedItem]:
        """Every rendered item in reading order, which the post-render check looks for
        in the PDF's text."""
        items: list[SelectedItem] = []
        if self.resume is not None:
            items.append(self.resume)
        for experience in self.experiences:
            items.append(experience)
            items.extend(experience.bullets)
        items.extend(self.formation)
        items.extend(self.competences)
        if self.options.loisirs:
            items.extend(self.loisirs)
        return items


def has_hobbies(profile: Profile) -> bool:
    return any(item.kind == "hobby" for item in profile.items)


def _of_kind(profile: Profile, kind: str) -> list[ProfileItem]:
    return [item for item in profile.items if item.kind == kind]


def _bullets_of(profile: Profile, experience_id: str) -> list[ProfileItem]:
    return [item for item in _of_kind(profile, "bullet") if item.parent_id == experience_id]


def _resume_item(profile: Profile) -> SelectedItem | None:
    # Each line of the section is an item: the summary is all of them, under the first id.
    lines = _of_kind(profile, "resume")
    if not lines:
        return None
    return SelectedItem(id=lines[0].id, text=" ".join(line.text for line in lines))


def known_ids(profile: Profile, ids: Collection[str]) -> list[str]:
    """`ids` in CV order, without those the CV no longer has."""
    return [item.id for item in profile.items if item.id in ids]


def page_of(
    profile: Profile,
    excluded_ids: Collection[str],
    options: CvOptions,
    blockers: OptionBlockers,
    manifest: CvManifest,
) -> CvPage:
    def item(source: ProfileItem) -> PageItem:
        return PageItem(id=source.id, text=source.text, selected=source.id not in excluded_ids)

    def experience(source: ProfileItem) -> PageExperience:
        headline, dates = split_title(source.text)
        return PageExperience(
            id=source.id,
            text=headline,
            dates=dates,
            selected=source.id not in excluded_ids,
            bullets=[item(bullet) for bullet in _bullets_of(profile, source.id)],
        )

    resume = _resume_item(profile)
    return CvPage(
        resume=(
            PageItem(id=resume.id, text=resume.text, selected=resume.id not in excluded_ids)
            if resume
            else None
        ),
        experiences=[experience(source) for source in _of_kind(profile, "experience")],
        formation=[
            PageFormation(
                id=source.id,
                text=source.text,
                selected=source.id not in excluded_ids,
                heading=source.heading,
            )
            for source in _of_kind(profile, "formation")
        ],
        competences=[item(source) for source in _of_kind(profile, "skill")],
        loisirs=[item(source) for source in _of_kind(profile, "hobby")],
        excluded_ids=known_ids(profile, excluded_ids),
        options=options.clamped_to(blockers),
        option_blockers=blockers,
        max_pages=manifest.max_pages,
    )


def build_selection(
    profile: Profile,
    excluded_ids: Collection[str],
    options: CvOptions,
    *,
    template: str,
    lang: str,
) -> CvSelection:
    """The items left on the page, in CV order. A bullet leaves with its experience."""

    def chosen(kind: str) -> list[SelectedItem]:
        return [
            SelectedItem(id=source.id, text=source.text)
            for source in _of_kind(profile, kind)
            if source.id not in excluded_ids
        ]

    resume = _resume_item(profile)
    return CvSelection(
        template=template,
        lang=lang,
        resume=resume if resume and resume.id not in excluded_ids else None,
        experiences=[
            SelectedExperience(
                id=experience.id,
                text=experience.text,
                bullets=[
                    SelectedItem(id=bullet.id, text=bullet.text)
                    for bullet in _bullets_of(profile, experience.id)
                    if bullet.id not in excluded_ids
                ],
            )
            for experience in _of_kind(profile, "experience")
            if experience.id not in excluded_ids
        ],
        formation=[
            SelectedFormation(id=source.id, text=source.text, heading=source.heading)
            for source in _of_kind(profile, "formation")
            if source.id not in excluded_ids
        ],
        competences=chosen("skill"),
        loisirs=chosen("hobby"),
        options=options,
    )

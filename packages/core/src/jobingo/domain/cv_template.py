from typing import Literal

from pydantic import BaseModel

type CvOptionName = Literal["photo", "panneau_competences", "loisirs"]
type CvSection = Literal["resume", "experiences", "formation", "competences", "loisirs"]


class SectionLimits(BaseModel):
    max_chars: int | None = None
    max_items: int | None = None
    max_bullets_per_item: int | None = None


class CvManifest(BaseModel):
    """A template's `manifest.yaml`. Templates ship with the code, so a bad one is a bug
    and fails on load. The stylesheet's `:root` holds the default colours.

    `sections` frames the model's proposal for an offer. The user's own choices on the
    CV page are not cut by it: the page count tells them when the CV is too long.
    """

    name: str
    langs: list[str]
    max_pages: int
    options: list[CvOptionName]
    sections: dict[CvSection, SectionLimits] = {}

    def limits(self, section: CvSection) -> SectionLimits:
        return self.sections.get(section, SectionLimits())

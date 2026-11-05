from typing import Literal

from pydantic import BaseModel

type CvOptionName = Literal["photo", "panneau_competences", "loisirs"]


class CvManifest(BaseModel):
    """A template's `manifest.yaml`. Templates ship with the code, so a bad one is a bug
    and fails on load. The stylesheet's `:root` holds the default colours."""

    name: str
    langs: list[str]
    max_pages: int
    options: list[CvOptionName]

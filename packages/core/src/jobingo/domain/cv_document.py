"""One CV document in its two views, and the two kinds of draft that can produce it."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from jobingo.domain.cv_diagnostics import CvDiagnostic, diagnose_cv, diagnose_fields
from jobingo.domain.cv_fields import CvFields, canonical_stored, fields_to_markdown, parse_fields
from jobingo.domain.cv_markdown import to_clean_view

type CvLang = Literal["fr"]


class TextDraft(BaseModel):
    mode: Literal["text"]
    text: str


class FormDraft(BaseModel):
    mode: Literal["form"]
    fields: CvFields


type CvDraft = Annotated[TextDraft | FormDraft, Field(discriminator="mode")]


class CvView(BaseModel):
    lang: CvLang
    text: str
    fields: CvFields
    diagnostics: list[CvDiagnostic]


class CvDocument(CvView):
    sha256: str | None  # of the stored content; None until the first save
    version: int  # 0 until the first save
    updated_at: datetime | None


def draft_markdown(draft: TextDraft | FormDraft, lang: CvLang) -> str:
    if isinstance(draft, TextDraft):
        return draft.text
    return fields_to_markdown(draft.fields, lang)


def view_of_stored(stored: str, lang: CvLang) -> CvView:
    clean = to_clean_view(stored)
    return CvView(lang=lang, text=clean, fields=parse_fields(clean), diagnostics=diagnose_cv(clean))


def convert_draft(draft: TextDraft | FormDraft, lang: CvLang) -> CvView:
    """Both views of a draft, as a save would lay them out. Ids are not visible, so
    this needs no previous version. Line numbers in the diagnostics are those of the
    text the user is looking at: the draft's own for a text draft, else the view's."""
    view = view_of_stored(canonical_stored(draft_markdown(draft, lang), "", lang), lang)
    if isinstance(draft, TextDraft):
        return view.model_copy(update={"diagnostics": diagnose_cv(draft.text)})
    return view.model_copy(update={"diagnostics": diagnose_fields(draft.fields) + view.diagnostics})

from pydantic import BaseModel

from jobingo.domain.letter import LetterProposal, LetterProposalSchema, SourceName
from jobingo.llm.client import Task, UntrustedText


class LetterSlotInput(BaseModel):
    name: str
    max_words: int
    sources: list[SourceName] = []


class AchievementInput(BaseModel):
    """One element of the CV the letter may draw on."""

    id: str
    text: str


class DraftLetterInput(BaseModel):
    lang: str
    offer_title: UntrustedText
    offer_company: UntrustedText
    offer_description: UntrustedText
    company_notes: UntrustedText = ""
    template_name: str
    slots: list[LetterSlotInput]
    achievements: list[AchievementInput]
    style_register: str = ""
    style_examples: list[str] = []
    style_forbidden: list[str] = []


DRAFT_LETTER_TASK: Task[DraftLetterInput, LetterProposal] = Task(
    name="draft_letter",
    tier="writing",
    input_model=DraftLetterInput,
    output_model=LetterProposal,
    user_template="draft_letter.v4.md",
    system_template="draft_letter.v4.system.md",
    prompt_version=4,
    schema_model=LetterProposalSchema,
    max_tokens=4000,
)

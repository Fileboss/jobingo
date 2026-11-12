from pydantic import BaseModel

from jobingo.domain.cv_proposal import CvRanking, CvRankingSchema
from jobingo.llm.client import Task, UntrustedText


class CvItemInput(BaseModel):
    """One element of the CV offered to the model, under a short alias (`E2.3`)."""

    id: str
    kind: str  # experience | bullet | project | formation | skill | hobby
    text: str
    tags: list[str] = []
    parent_id: str | None = None


class SelectCvContentInput(BaseModel):
    lang: str
    offer_title: UntrustedText
    offer_company: UntrustedText
    offer_description: UntrustedText
    template_name: str
    max_resume_chars: int | None = None
    max_experiences: int | None = None
    max_bullets_per_experience: int | None = None
    max_formation: int | None = None
    max_competences: int | None = None
    max_projets: int | None = None
    max_loisirs: int | None = None
    resume: str = ""
    items: list[CvItemInput] = []
    style_register: str = ""
    style_examples: list[str] = []
    style_forbidden: list[str] = []


SELECT_CV_CONTENT_TASK: Task[SelectCvContentInput, CvRanking] = Task(
    name="select_cv_content",
    tier="writing",
    input_model=SelectCvContentInput,
    output_model=CvRanking,
    user_template="select_cv_content.v14.md",
    system_template="select_cv_content.v14.system.md",
    prompt_version=14,
    schema_model=CvRankingSchema,
    max_tokens=8000,
)

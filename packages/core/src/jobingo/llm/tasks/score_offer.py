from pydantic import BaseModel, Field

from jobingo.llm.client import Task, UntrustedText


class ScoreOfferInput(BaseModel):
    title: UntrustedText
    company_name: UntrustedText
    location: UntrustedText
    contract: str
    remote: str
    salary_min: int | None
    salary_max: int | None
    description_md: UntrustedText
    objectives_preferences: str
    profile_tags: list[str]


class ScoreOfferOutput(BaseModel):
    mission: float = Field(ge=0, le=10)
    stack: float = Field(ge=0, le=10)
    salary: float = Field(ge=0, le=10)
    culture: float = Field(ge=0, le=10)
    strengths: list[str] = []
    gaps: list[str] = []
    summary: str = ""


SCORE_OFFER_TASK: Task[ScoreOfferInput, ScoreOfferOutput] = Task(
    name="score_offer",
    tier="fast",
    input_model=ScoreOfferInput,
    output_model=ScoreOfferOutput,
    user_template="score_offer.v1.md",
    prompt_version=1,
    max_tokens=1024,
)

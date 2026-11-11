from pydantic import BaseModel

from jobingo.domain.offers import ExtractedOffer
from jobingo.llm.client import Task, UntrustedText


class ExtractOfferInput(BaseModel):
    text: UntrustedText


class ExtractOfferOutput(BaseModel):
    offers: list[ExtractedOffer]


EXTRACT_OFFER_TASK: Task[ExtractOfferInput, ExtractOfferOutput] = Task(
    name="extract_offer",
    tier="fast",
    input_model=ExtractOfferInput,
    output_model=ExtractOfferOutput,
    user_template="extract_offer.v3.md",
    system_template="extract_offer.v3.system.md",
    prompt_version=3,
    max_tokens=8192,
)

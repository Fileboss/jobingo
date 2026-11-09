"""Drafting a reply: what the user wants it to do, and what to flag beside the draft."""

from typing import Literal

from pydantic import BaseModel, Field

from jobingo.domain.placeholders import find_placeholders, placeholders_message
from jobingo.domain.style import StyleGuide, forbidden_hits
from jobingo.domain.text_checks import numbers_in

type Intent = Literal[
    "decliner", "accepter_entretien", "demander_precisions", "relancer", "remercier", "candidater"
]

INTENT_LABELS: dict[Intent, str] = {
    "decliner": "Décliner poliment",
    "accepter_entretien": "Accepter un entretien",
    "demander_precisions": "Demander des précisions",
    "relancer": "Relancer",
    "remercier": "Remercier après un entretien",
    # Answering the e-mail an offer came in, with the CV and the letter attached.
    "candidater": "Envoyer ma candidature",
}


class ReplyRequest(BaseModel):
    intent: Intent
    # What the user wants said: their availabilities, a reason. Redacted like the rest.
    instruction: str = Field(default="", max_length=2000)


class ReplyDraft(BaseModel):
    subject: str
    body: str
    notes: str
    # Shown beside the draft. None blocks: the user edits, and the queue checks again.
    warnings: list[str]
    llm_call_id: int


def reply_warnings(body: str, style: StyleGuide, sources: str) -> list[str]:
    """What is worth checking in a draft: a forbidden phrase, a number found in neither
    the message nor the instruction, a gap left to fill (which the queue refuses)."""
    warnings = [
        f"tournure interdite : « {phrase} »" for phrase in forbidden_hits(body, style.forbidden)
    ]
    known = set(numbers_in(sources))
    unknown = [n for n in dict.fromkeys(numbers_in(body)) if n not in known]
    if unknown:
        warnings.append(f"nombre absent du message et de la consigne : {', '.join(unknown)}")
    placeholders = find_placeholders(body)
    if placeholders:
        warnings.append(placeholders_message(placeholders))
    return warnings

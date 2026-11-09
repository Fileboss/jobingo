"""The approval queue: a message that leaves is first an action, frozen, previewed and
approved by a click on exactly what will be sent."""

import hashlib
import json
import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

type ActionStatus = Literal["proposed", "approved", "sending", "sent", "failed", "rejected"]
type DocumentKind = Literal["cv", "letter"]

_ADDRESS = re.compile(r"^[^@\s<>,;\"]+@[^@\s<>,;\"]+\.[^@\s<>,;\"]+$")


def is_valid_address(address: str) -> bool:
    return bool(_ADDRESS.match(address))


class Attachment(BaseModel):
    document_id: int
    filename: str
    sha256: str


class SendEmailPayload(BaseModel):
    """Everything that leaves, frozen at proposal. The sender's name is the identity's,
    put in by code: this payload never reaches the model. `message_id` is generated
    once, so a retry sends the same Message-ID."""

    from_name: str
    from_addr: str
    to: list[str]
    cc: list[str] = []
    subject: str
    body_text: str
    in_reply_to: str = ""
    references: list[str] = []
    attachments: list[Attachment] = []
    message_id: str


def canonical_json(payload: SendEmailPayload) -> str:
    return json.dumps(
        payload.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def payload_hash(payload: SendEmailPayload) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


# --- what the client sends and sees ----------------------------------------------

Address = Annotated[str, StringConstraints(strip_whitespace=True, max_length=254)]


class AttachmentRequest(BaseModel):
    """A letter of the application, or the CV: adapted to its offer when there is a
    draft for it, else the CV page as it stands."""

    kind: DocumentKind
    letter_id: int | None = None


class EmailProposal(BaseModel):
    # The application it concerns, and the received message it answers, if any.
    application_id: int | None = None
    message_id: int | None = None
    to: list[Address] = Field(min_length=1, max_length=10)
    cc: list[Address] = Field(default=[], max_length=10)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20_000)
    attachments: list[AttachmentRequest] = Field(default=[], max_length=5)
    # The model call the text was drafted from, when it was.
    llm_call_id: int | None = None


class Approval(BaseModel):
    # The hash of the payload on screen: approving anything else is refused.
    payload_hash: str


class ActionSummary(BaseModel):
    id: int
    status: ActionStatus
    to: list[str]
    subject: str
    application_id: int | None
    application_title: str | None
    attachments: int
    dry_run: bool | None
    created_at: datetime
    sent_at: datetime | None


class ActionView(ActionSummary):
    payload: SendEmailPayload
    payload_hash: str
    message_id: int | None
    llm_call_id: int | None
    error: str | None
    decided_at: datetime | None

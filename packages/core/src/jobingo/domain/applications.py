"""Applications and their timeline. The status is never written: it is derived from the
events in date order, so it can always be explained by what happened."""

from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from jobingo.domain.mail import Category

type EventType = Literal[
    "applied",
    "message_received",
    "message_sent",
    "interview_scheduled",
    "interview_done",
    "offer_received",
    "rejected",
    "withdrawn",
    "note",
]
type Status = Literal["a_postuler", "postule", "en_echange", "entretien", "offre", "cloture"]
type Tone = Literal["todo", "active", "final", "lost"]

FOLLOW_UP_DELAY = timedelta(days=7)

# The events that move the status. A note never does.
_STATUS_BY_EVENT: dict[EventType, Status] = {
    "applied": "postule",
    "message_received": "en_echange",
    "message_sent": "en_echange",
    "interview_scheduled": "entretien",
    "interview_done": "entretien",
    "offer_received": "offre",
    "rejected": "cloture",
    "withdrawn": "cloture",
}
_MESSAGES: frozenset[EventType] = frozenset({"message_received", "message_sent"})
_BEFORE_EXCHANGE: frozenset[Status] = frozenset({"a_postuler", "postule"})


class ApplicationEvent(BaseModel):
    id: int
    type: EventType
    occurred_at: date
    note: str
    created_at: datetime
    # The message it came from: received, or a suggestion accepted.
    message_id: int | None = None
    # The send it records.
    action_id: int | None = None


class NewEvent(BaseModel):
    type: EventType
    occurred_at: date
    note: str = Field(default="", max_length=2000)


def _significant(events: list[ApplicationEvent]) -> list[ApplicationEvent]:
    return sorted(
        (e for e in events if e.type in _STATUS_BY_EVENT), key=lambda e: (e.occurred_at, e.id)
    )


def derive_status(events: list[ApplicationEvent]) -> Status:
    """Each significant event sets the status in date order, except a message, which
    only moves an application into « en échange »: a late automated mail must not
    reopen a closed application, nor take one at the interview back a step."""
    status: Status = "a_postuler"
    for event in _significant(events):
        if event.type in _MESSAGES and status not in _BEFORE_EXCHANGE:
            continue
        status = _STATUS_BY_EVENT[event.type]
    return status


def next_follow_up(events: list[ApplicationEvent]) -> date | None:
    """A week after sending the application, if nothing has happened since."""
    significant = _significant(events)
    if not significant or significant[-1].type != "applied":
        return None
    return significant[-1].occurred_at + FOLLOW_UP_DELAY


def tone(status: Status, events: list[ApplicationEvent]) -> Tone:
    """How far along it is: nothing done yet, running, at the end (an offer, or an
    interview done and only the answer left), or lost."""
    if status == "cloture":
        return "lost"
    if status == "offre":
        return "final"
    if status == "a_postuler":
        return "todo"
    steps = [e for e in _significant(events) if e.type not in _MESSAGES]
    if steps and steps[-1].type == "interview_done":
        return "final"
    return "active"


class Contact(BaseModel):
    """Someone at the company: third-party data, used to address a message, never put
    in a prompt on its own."""

    name: str = Field(default="", max_length=200)
    email: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, max_length=254, pattern=r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$"
        ),
    ] = ""
    phone: str = Field(default="", max_length=50)


class NewApplication(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    company_name: str = Field(default="", max_length=300)


class ApplicationSummary(BaseModel):
    id: int
    offer_id: int | None
    title: str
    company_name: str
    status: Status
    tone: Tone
    last_event: ApplicationEvent | None
    follow_up_on: date | None
    created_at: datetime


class LinkedMessage(BaseModel):
    id: int
    from_addr: str
    subject: str
    received_at: datetime
    category: Category | None


class ApplicationView(ApplicationSummary):
    contact: Contact
    # What the user knows about the company: a source for the letter's facts.
    company_notes: str
    events: list[ApplicationEvent]  # newest first
    messages: list[LinkedMessage]  # newest first

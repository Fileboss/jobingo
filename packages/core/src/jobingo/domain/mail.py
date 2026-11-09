"""Mail as the app stores it: one row per message read, sorted into job alerts and
messages to classify."""

import re
from datetime import date, datetime
from difflib import SequenceMatcher
from email.utils import parseaddr
from typing import Literal

from pydantic import BaseModel

from jobingo.domain.text import fold

# `alert`: a job alert, read for its offers. `message`: anything else, to classify.
type MessageKind = Literal["alert", "message"]
# The model's verdict on a message.
type Category = Literal["offer", "rejection", "interview", "recruiter_other", "other"]
# Why a message is out of the list. The first two are rules, applied without the model.
type HiddenReason = Literal["newsletter", "blocked_sender", "other", "user"]
type LinkedBy = Literal["match", "user"]
type SuggestionType = Literal["rejected", "interview_scheduled"]
type SuggestionStatus = Literal["pending", "accepted", "dismissed"]

# The only status changes a message may suggest. They become events on a click only.
SUGGESTED_EVENT: dict[Category, SuggestionType] = {
    "rejection": "rejected",
    "interview": "interview_scheduled",
}
# The categories that concern an application, and are matched to one at sync time. An
# offer is a new job, not news of an application.
MATCHED_CATEGORIES: frozenset[Category] = frozenset({"rejection", "interview", "recruiter_other"})

# Above this, a company named in a message is a company applied to.
COMPANY_SIMILARITY_THRESHOLD = 0.9


class RawMessage(BaseModel):
    """One message as the connector read it, before anything is decided about it."""

    uid: int
    message_id: str
    from_addr: str
    to_addrs: str = ""
    subject: str
    received_at: datetime
    body_text: str = ""
    body_html: str = ""
    in_reply_to: str = ""
    references: list[str] = []
    list_unsubscribe: bool = False

    @property
    def thread_id(self) -> str:
        """The first message of the thread: what a reply and its answers share."""
        if self.references:
            return self.references[0]
        return self.in_reply_to or self.message_id


class FetchResult(BaseModel):
    # Changes when the server renumbers the folder: the UIDs known so far mean nothing.
    uidvalidity: str
    messages: list[RawMessage]
    # More messages wait above the last one returned, for the next sync.
    has_more: bool = False


class Suggestion(BaseModel):
    type: SuggestionType
    # The interview's day, when the message gives it; else the event takes the day received.
    date: date | None
    status: SuggestionStatus


class MessageSummary(BaseModel):
    id: int
    folder: str
    from_addr: str
    subject: str
    received_at: datetime
    kind: MessageKind | None
    # Offers read from it: an alert's, or a recruiter's message describing a job.
    offer_count: int
    excerpt: str
    category: Category | None
    # One sentence by the model, in French.
    summary: str
    hidden_reason: HiddenReason | None
    application_id: int | None
    application_title: str | None
    suggestion: Suggestion | None


class Message(MessageSummary):
    to_addrs: str
    # The text only: the HTML part is kept for the alert reader, never shown.
    body_text: str
    offer_ids: list[int]
    processed_at: datetime | None
    # The company the model read in it, matched against the applications.
    company_hint: str
    linked_by: LinkedBy | None
    llm_call_id: int | None


class FolderState(BaseModel):
    folder: str
    synced_at: datetime | None


class MailboxStatus(BaseModel):
    # The address read, and whether it is the local demo server rather than a real one.
    address: str
    host: str
    local: bool
    dry_run: bool
    folders: list[FolderState]
    # Stored messages waiting for the model: alerts from other senders than LinkedIn,
    # and messages to classify.
    waiting: int
    # Status changes suggested by a message tied to an application, not yet decided.
    suggestions: int


class SyncReport(BaseModel):
    fetched: int = 0
    # Read again because the server renumbered a folder, already stored.
    duplicates: int = 0
    alerts: int = 0
    # Messages the model classified, and those hidden by a rule without it.
    classified: int = 0
    hidden: int = 0
    # Messages tied to an application by code.
    linked: int = 0
    offer_ids: list[int] = []
    # Offers stored but not scored, because the model is not configured or a call failed.
    unscored_ids: list[int] = []
    # Alerts and messages left for the next sync: no model, or a call that failed.
    waiting: int = 0
    has_more: bool = False
    # Why the model part stopped, in French; the stored messages are kept.
    error: str | None = None


def bare_address(header: str) -> str:
    """`Alex Moreau <alex@jobingo.test>` → `alex@jobingo.test`, lowercased."""
    return parseaddr(header)[1].strip().lower()


def excerpt(text: str, length: int = 160) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= length else flat[: length - 1].rstrip() + "…"


def parse_iso_date(value: str | None) -> date | None:
    """The model's date, or None for anything that is not one."""
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


_NAME_NOISE = re.compile(r"[^a-z0-9]+")
_LEGAL_FORMS = frozenset({"sas", "sarl", "sa", "inc", "ltd", "gmbh", "group", "groupe"})


def _company_words(name: str) -> str:
    words = _NAME_NOISE.sub(" ", fold(name)).split()
    return " ".join(word for word in words if word not in _LEGAL_FORMS)


def company_similarity(a: str, b: str) -> float:
    """0 to 1, ignoring case, accents, punctuation and legal forms: `Voltéo SAS` is
    `volteo`."""
    left, right = _company_words(a), _company_words(b)
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()

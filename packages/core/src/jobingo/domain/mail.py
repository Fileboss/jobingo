"""Mail as the app stores it: one row per message read, sorted into job alerts and
messages to classify."""

from datetime import datetime
from email.utils import parseaddr
from typing import Literal

from pydantic import BaseModel

# `alert`: a job alert, read for its offers. `message`: anything else, to classify.
type MessageKind = Literal["alert", "message"]


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


class MessageSummary(BaseModel):
    id: int
    folder: str
    from_addr: str
    subject: str
    received_at: datetime
    kind: MessageKind | None
    # Offers read from it, when it is an alert.
    offer_count: int
    excerpt: str


class Message(MessageSummary):
    to_addrs: str
    # The text only: the HTML part is kept for the alert reader, never shown.
    body_text: str
    offer_ids: list[int]
    processed_at: datetime | None


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
    # Stored messages waiting for the model: alerts from other senders than LinkedIn.
    waiting: int


class SyncReport(BaseModel):
    fetched: int = 0
    # Read again because the server renumbered a folder, already stored.
    duplicates: int = 0
    alerts: int = 0
    offer_ids: list[int] = []
    # Offers stored but not scored, because the model is not configured or a call failed.
    unscored_ids: list[int] = []
    # Alerts left for the next sync: no model, or a call that failed.
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

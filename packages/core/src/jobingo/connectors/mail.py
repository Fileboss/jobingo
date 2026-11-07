"""Reading mail: what a mailbox gives, and how its raw bytes become a `RawMessage`."""

import re
from datetime import UTC, date, datetime
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from typing import Protocol

from bs4 import BeautifulSoup

from jobingo.domain.mail import FetchResult, RawMessage

_MSGID_RE = re.compile(r"<[^<>\s]+>")
# Postgres text cannot hold NUL, and a body past these sizes is not a job message.
_MAX_TEXT = 100_000
_MAX_HTML = 500_000


class MailboxError(Exception):
    """The mailbox could not be read. The message is shown to the user, in French."""


class MailSource(Protocol):
    @property
    def address(self) -> str: ...

    @property
    def host(self) -> str: ...

    def fetch(self, folder: str, after_uid: int, since: date | None, limit: int) -> FetchResult:
        """Up to `limit` messages of `folder`, oldest first: those whose UID is above
        `after_uid`, or when it is 0, those received since `since` (all if None)."""
        ...


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    return re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True))


def _clean(value: str, limit: int) -> str:
    return value.replace("\x00", "")[:limit]


def _header(message: EmailMessage, name: str) -> str:
    try:
        value = message.get(name)
    except (ValueError, IndexError):  # a malformed header the parser cannot decode
        return ""
    return _clean(str(value).strip(), 2000) if value is not None else ""


def _part_text(message: EmailMessage, subtype: str) -> str:
    part = message.get_body(preferencelist=(subtype,))
    if part is None or not isinstance(part, EmailMessage):
        return ""
    try:
        content = part.get_content()
    except (LookupError, ValueError):  # an unknown charset: read what can be read
        payload = part.get_payload(decode=True)
        content = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else ""
    return content if isinstance(content, str) else ""


def _received_at(message: EmailMessage) -> datetime:
    try:
        sent = parsedate_to_datetime(_header(message, "date"))
    except (TypeError, ValueError):
        return datetime.now(UTC)
    return sent.astimezone(UTC) if sent.tzinfo else sent.replace(tzinfo=UTC)


def parse_message(uid: int, raw: bytes, fallback_id: str) -> RawMessage:
    """`fallback_id` stands for the Message-ID when a message has none."""
    message = message_from_bytes(raw, _class=EmailMessage, policy=policy.default)
    html = _part_text(message, "html")
    text = _part_text(message, "plain") or (html_to_text(html) if html else "")
    return RawMessage(
        uid=uid,
        message_id=_header(message, "message-id") or fallback_id,
        from_addr=_header(message, "from"),
        to_addrs=_header(message, "to"),
        subject=_header(message, "subject"),
        received_at=_received_at(message),
        body_text=_clean(text, _MAX_TEXT),
        body_html=_clean(html, _MAX_HTML),
        in_reply_to=_header(message, "in-reply-to"),
        references=_MSGID_RE.findall(_header(message, "references")),
        list_unsubscribe=bool(_header(message, "list-unsubscribe")),
    )

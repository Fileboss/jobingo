"""The mailbox over IMAP: Gmail with an app password, or the local GreenMail server.

Read-only by construction: folders are opened with EXAMINE and bodies fetched with
BODY.PEEK, so reading marks nothing as seen, and this module has no way to move, flag
or delete a message."""

import imaplib
import re
import ssl
from datetime import date
from itertools import batched
from typing import cast

from jobingo.connectors.mail import MailboxError, parse_message
from jobingo.domain.mail import FetchResult, RawMessage

_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
_UID_RE = re.compile(rb"\bUID (\d+)")
# IMAP dates use English month names, whatever the locale.
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_FETCH_BATCH = 25


def _imap_date(day: date) -> str:
    return f"{day.day:02d}-{_MONTHS[day.month - 1]}-{day.year}"


def _quoted(folder: str) -> str:
    if not folder.isascii():
        # Non-ASCII names need IMAP's modified UTF-7, not written here.
        raise MailboxError(f"Le nom de dossier « {folder} » doit être en ASCII.")
    return '"' + folder.replace("\\", "\\\\").replace('"', '\\"') + '"'


class ImapMailbox:
    def __init__(
        self, host: str, port: int, use_ssl: bool, user: str, password: str, timeout: float = 20
    ) -> None:
        if not use_ssl and host not in _LOOPBACK:
            # The password would cross the network in clear text.
            raise MailboxError(
                "IMAP sans SSL n'est permis que vers cette machine : activez MAIL_IMAP_SSL."
            )
        self._host = host
        self._port = port
        self._ssl = use_ssl
        self._user = user
        self._password = password
        self._timeout = timeout

    @property
    def address(self) -> str:
        return self._user

    @property
    def host(self) -> str:
        return self._host

    def _connect(self) -> imaplib.IMAP4:
        if self._ssl:
            return imaplib.IMAP4_SSL(
                self._host,
                self._port,
                ssl_context=ssl.create_default_context(),
                timeout=self._timeout,
            )
        return imaplib.IMAP4(self._host, self._port, timeout=self._timeout)

    def fetch(self, folder: str, after_uid: int, since: date | None, limit: int) -> FetchResult:
        try:
            with self._connect() as imap:
                return self._fetch(imap, folder, after_uid, since, limit)
        except imaplib.IMAP4.error as error:
            raise MailboxError(f"Le serveur IMAP a refusé la lecture : {error}") from None
        except OSError as error:  # refused, unreachable, timed out, TLS failed
            raise MailboxError(
                f"Le serveur IMAP {self._host}:{self._port} est injoignable ({error})."
            ) from None

    def _fetch(
        self, imap: imaplib.IMAP4, folder: str, after_uid: int, since: date | None, limit: int
    ) -> FetchResult:
        imap.login(self._user, self._password)
        status, _ = imap.select(_quoted(folder), readonly=True)
        if status != "OK":
            raise MailboxError(f"Le dossier « {folder} » est introuvable dans la boîte.")
        _, validity = imap.response("UIDVALIDITY")
        uidvalidity = validity[0].decode() if validity and validity[0] else ""

        if after_uid:
            criteria = ["UID", f"{after_uid + 1}:*"]
        elif since is not None:
            criteria = ["SINCE", _imap_date(since)]
        else:
            criteria = ["ALL"]
        _, found = imap.uid("SEARCH", *criteria)
        # `N:*` always returns the last message, even when its UID is below N.
        uids = sorted(int(uid) for uid in (found[0] or b"").split() if int(uid) > after_uid)

        messages: list[RawMessage] = []
        for chunk in batched(uids[:limit], _FETCH_BATCH):
            _, data = imap.uid("FETCH", ",".join(map(str, chunk)), "(UID BODY.PEEK[])")
            for item in data:
                # A message comes as (b'1 (UID 5 BODY[] {385}', raw bytes), then b')'.
                if not isinstance(item, tuple):
                    continue
                envelope, raw = cast(tuple[bytes, bytes], item)
                match = _UID_RE.search(envelope)
                if match is None:
                    continue
                uid = int(match.group(1))
                fallback = f"<uid-{uidvalidity}-{uid}@{folder}.{self._host}>"
                messages.append(parse_message(uid, raw, fallback))
        messages.sort(key=lambda message: message.uid)
        return FetchResult(uidvalidity=uidvalidity, messages=messages, has_more=len(uids) > limit)

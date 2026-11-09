"""Sending mail. Only `hitl.executor` imports this module, which an import contract and
a hook enforce: no code path that calls the model can send."""

import smtplib
import ssl
from email.message import EmailMessage
from typing import Protocol

_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


class SendError(Exception):
    """The server refused or could not be reached. The message is shown, in French."""


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None: ...


class SmtpSender:
    """SMTP over TLS from the first byte (port 465, as Gmail with an app password), or
    plain SMTP to a server on this machine only, such as the local Mailpit: a password
    never crosses the network in clear."""

    def __init__(
        self, host: str, port: int, use_ssl: bool, user: str = "", password: str = ""
    ) -> None:
        if not use_ssl and host not in _LOOPBACK:
            raise SendError(
                f"SMTP sans chiffrement vers {host} : réglez MAIL_SMTP_SSL=1, "
                "seul un serveur local peut s'en passer."
            )
        self._host, self._port, self._ssl = host, port, use_ssl
        self._user, self._password = user, password

    def send(self, message: EmailMessage) -> None:
        try:
            smtp = (
                smtplib.SMTP_SSL(
                    self._host, self._port, context=ssl.create_default_context(), timeout=30
                )
                if self._ssl
                else smtplib.SMTP(self._host, self._port, timeout=30)
            )
            with smtp:
                if self._user:
                    smtp.login(self._user, self._password)
                smtp.send_message(message)
        except smtplib.SMTPAuthenticationError:
            raise SendError("Le serveur SMTP refuse l'identifiant ou le mot de passe.") from None
        except (OSError, smtplib.SMTPException) as error:
            raise SendError(
                f"Le serveur SMTP {self._host}:{self._port} n'a pas accepté le message "
                f"({type(error).__name__})."
            ) from None

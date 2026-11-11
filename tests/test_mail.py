"""Reading mail, against the real local IMAP server (GreenMail, `make mail-up`): each
test gets its own mailbox, which GreenMail creates on the first delivery."""

import imaplib
import smtplib
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from jobingo.config import Settings
from jobingo.connectors.imap import ImapMailbox
from jobingo.connectors.mail import MailboxError, parse_message
from jobingo.db import Conn
from jobingo.domain.linkedin_alert import is_linkedin_sender, parse_linkedin_alert
from jobingo.domain.offers import ExtractedOffer
from jobingo.llm.fake import FakeLLMClient
from jobingo.llm.tasks.extract_offer import ExtractOfferOutput
from jobingo.llm.tasks.score_offer import ScoreOfferOutput

HOST, SMTP_PORT, IMAP_PORT = "127.0.0.1", 3025, 3143

FIXTURES = Path(__file__).parent / "fixtures"
LINKEDIN_ALERT = (FIXTURES / "linkedin_alert.html").read_text(encoding="utf-8")
CV = (FIXTURES / "cv.fr.md").read_text(encoding="utf-8")
LINKEDIN_SENDER = "LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>"


# --- the alert reader, in code --------------------------------------------------


def test_an_alert_gives_each_job_card_once():
    offers = parse_linkedin_alert(LINKEDIN_ALERT)
    assert [(o.job_id, o.title, o.company_name, o.location) for o in offers] == [
        ("3901234567", "Ingénieur logiciel Python", "Plume Énergie", "Lyon, Auvergne-Rhône-Alpes"),
        ("3907654321", "Data engineer", "Voltéo", "Paris (Hybride)"),
    ]


def test_an_alert_link_is_rebuilt_without_tracking():
    assert parse_linkedin_alert(LINKEDIN_ALERT)[0].url == (
        "https://www.linkedin.com/jobs/view/3901234567"
    )


def test_links_that_are_not_jobs_are_ignored():
    assert parse_linkedin_alert("<a href='https://www.linkedin.com/feed'>Fil</a>") == []


def test_the_sender_is_the_address_not_the_display_name():
    assert is_linkedin_sender(LINKEDIN_SENDER)
    assert not is_linkedin_sender("jobs@notlinkedin.com.evil.test")
    assert not is_linkedin_sender('"x@linkedin.com" <alerts@evil.test>')


# --- parsing raw mail ------------------------------------------------------------


def _mail(**headers: str) -> EmailMessage:
    message = EmailMessage()
    for name, value in headers.items():
        message[name.replace("_", "-")] = value
    return message


def test_a_message_is_decoded_and_its_thread_found():
    message = _mail(
        From="Camille Roux <camille@voltéo.test>",
        To="alex@jobingo.test",
        Subject="Votre candidature – entretien ?",
        Message_ID="<b2@volteo.test>",
        In_Reply_To="<a1@jobingo.test>",
        References="<a0@jobingo.test> <a1@jobingo.test>",
        Date=format_datetime(datetime(2026, 11, 6, 9, 30, tzinfo=UTC)),
    )
    message.set_content("Bonjour Alex,\nseriez-vous disponible jeudi ?\x00")

    raw = parse_message(7, message.as_bytes(), "<fallback>")

    assert raw.subject == "Votre candidature – entretien ?"
    assert raw.message_id == "<b2@volteo.test>"
    assert raw.thread_id == "<a0@jobingo.test>"
    assert raw.received_at == datetime(2026, 11, 6, 9, 30, tzinfo=UTC)
    assert "\x00" not in raw.body_text  # Postgres text cannot hold it
    assert raw.body_text.startswith("Bonjour Alex")


def test_an_html_only_message_gets_a_text_body_and_a_missing_id_a_stand_in():
    message = _mail(From="rh@plume.test", Subject="Offre")
    message.set_content(
        "<html><head><style>p{}</style></head><body><p>Poste</p><script>x()</script></body></html>",
        subtype="html",
    )
    raw = parse_message(3, message.as_bytes(), "<uid-1-3@INBOX.local>")
    assert raw.body_text == "Poste"
    assert raw.message_id == "<uid-1-3@INBOX.local>"
    assert raw.thread_id == "<uid-1-3@INBOX.local>"


def test_imap_without_ssl_is_refused_beyond_this_machine():
    with pytest.raises(MailboxError, match="MAIL_IMAP_SSL"):
        ImapMailbox("imap.gmail.com", 143, False, "alex@jobingo.test", "secret")


# --- syncing a real mailbox ------------------------------------------------------


@dataclass
class Mailbox:
    address: str
    delivered: int = 0

    def deliver(self, message: EmailMessage) -> None:
        message["To"] = self.address
        with smtplib.SMTP(HOST, SMTP_PORT, timeout=5) as smtp:
            smtp.send_message(message)
        self._wait_for(message)

    def append(self, folder: str, message: EmailMessage, received: datetime) -> None:
        """Put a message straight in a folder, as a mail filter would, with its date."""
        message["To"] = self.address
        imap = self.imap()
        imap.create(f'"{folder}"')
        imap.append(f'"{folder}"', "", imaplib.Time2Internaldate(received), message.as_bytes())
        imap.logout()

    def imap(self) -> imaplib.IMAP4:
        imap = imaplib.IMAP4(HOST, IMAP_PORT, timeout=5)
        imap.login(self.address, self.address)
        return imap

    def _wait_for(self, message: EmailMessage) -> None:
        # Delivery is asynchronous: wait until the inbox holds one more message.
        self.delivered += 1
        for _ in range(100):
            try:
                imap = self.imap()
            except imaplib.IMAP4.error:  # the account appears with its first mail
                time.sleep(0.05)
                continue
            _, count = imap.select("INBOX", readonly=True)
            imap.logout()
            if count[0] and int(count[0]) >= self.delivered:
                return
            time.sleep(0.05)
        raise AssertionError(f"not delivered: {message['Subject']}")


@pytest.fixture
def mailbox() -> Mailbox:
    for attempt in range(20):  # it takes a few seconds to start, in CI
        try:
            with smtplib.SMTP(HOST, SMTP_PORT, timeout=2):
                break
        except OSError as error:
            if attempt == 19:
                pytest.fail(f"GreenMail is unreachable, run `make mail-up`: {error}")
            time.sleep(0.5)
    return Mailbox(f"alex-{uuid4().hex[:10]}@jobingo.test")


@pytest.fixture
def settings(settings: Settings, mailbox: Mailbox) -> Settings:
    """The test's own mailbox; GreenMail's password for it is the address."""
    return settings.model_copy(
        update={
            "mail_imap_user": mailbox.address,
            "mail_imap_password": SecretStr(mailbox.address),
        }
    )


@pytest.fixture
def no_model(client: TestClient) -> Iterator[None]:
    client.app.state.llm_client = None  # type: ignore[attr-defined]
    yield


def _alert(subject: str = "Nouvelles offres pour « python »") -> EmailMessage:
    message = _mail(From=LINKEDIN_SENDER, Subject=subject)
    message.set_content("Vos offres du jour.")
    message.add_alternative(LINKEDIN_ALERT, subtype="html")
    return message


def _recruiter(subject: str = "Votre profil nous intéresse") -> EmailMessage:
    message = _mail(From="Camille Roux <camille@volteo.test>", Subject=subject)
    message.set_content("Bonjour, seriez-vous disponible pour un échange ?")
    return message


def _sync(client: TestClient) -> Any:
    response = client.post("/api/mail/sync")
    assert response.status_code == 200, response.text
    return response.json()


def test_a_linkedin_alert_becomes_offers_without_the_model(
    client: TestClient, mailbox: Mailbox, no_model: None
):
    mailbox.deliver(_alert())
    mailbox.deliver(_recruiter())

    report = _sync(client)

    assert report["fetched"] == 2
    assert report["alerts"] == 1
    assert len(report["offer_ids"]) == 2
    assert report["unscored_ids"] == report["offer_ids"]  # no model: stored, not scored
    offers = {o["title"]: o for o in client.get("/api/offers").json()}
    assert offers["Data engineer"]["company_name"] == "Voltéo"
    assert offers["Data engineer"]["llm_call_id"] is None
    assert offers["Data engineer"]["state"] == "new"

    messages = client.get("/api/mail/messages").json()
    assert {m["kind"] for m in messages} == {"alert", "message"}
    [alert] = client.get("/api/mail/messages", params={"kind": "alert"}).json()
    assert alert["offer_count"] == 2
    detail = client.get(f"/api/mail/messages/{alert['id']}").json()
    assert sorted(detail["offer_ids"]) == sorted(report["offer_ids"])
    assert detail["processed_at"] is not None
    assert "body_html" not in detail  # the HTML part is never sent to the client
    assert {o["message_id"] for o in offers.values()} == {alert["id"]}


def test_a_second_sync_reads_only_what_is_new(client: TestClient, mailbox: Mailbox, no_model: None):
    mailbox.deliver(_alert())
    _sync(client)
    mailbox.deliver(_alert("Encore des offres pour « python »"))

    report = _sync(client)

    assert report["fetched"] == 1
    # The same jobs again: known offers, completed, not duplicated.
    assert len(client.get("/api/offers").json()) == 2
    assert len(client.get("/api/mail/messages").json()) == 2


def test_reading_marks_nothing_as_seen(client: TestClient, mailbox: Mailbox, no_model: None):
    mailbox.deliver(_recruiter())
    _sync(client)

    imap = mailbox.imap()
    imap.select("INBOX", readonly=True)
    _, unseen = imap.search(None, "UNSEEN")
    imap.logout()
    assert unseen[0].split() == [b"1"]


def test_a_renumbered_folder_is_read_again_without_duplicates(
    client: TestClient, conn: Conn, mailbox: Mailbox, no_model: None
):
    mailbox.deliver(_recruiter())
    _sync(client)
    conn.execute("UPDATE mail_folders SET uidvalidity = 'before-renumbering'")

    report = _sync(client)

    assert (report["fetched"], report["duplicates"]) == (0, 1)
    assert len(client.get("/api/mail/messages").json()) == 1


def test_the_first_sync_reads_the_last_30_days_only(
    client: TestClient, mailbox: Mailbox, settings: Settings, no_model: None
):
    now = datetime.now(UTC)
    mailbox.append("INBOX", _recruiter("Ancien message"), now - timedelta(days=45))
    mailbox.append("INBOX", _recruiter("Message récent"), now - timedelta(days=2))

    _sync(client)

    assert [m["subject"] for m in client.get("/api/mail/messages").json()] == ["Message récent"]


@pytest.fixture
def alert_folder(client: TestClient, settings: Settings) -> str:
    """A filter moves alerts out of the inbox, into their own folder."""
    folder = "Alertes-emploi"
    client.app.state.settings = settings.model_copy(update={"mail_alert_folder": folder})  # type: ignore[attr-defined]
    return folder


def _other_alert() -> EmailMessage:
    message = _mail(From="Alertes <alertes@emplois.test>", Subject="3 nouvelles offres")
    message.set_content("Tech Lead chez Voltéo, CDI à Lyon. Postuler sur emplois.test.")
    return message


def test_another_senders_alert_waits_for_the_model(
    client: TestClient, mailbox: Mailbox, alert_folder: str, no_model: None
):
    mailbox.append(alert_folder, _other_alert(), datetime.now(UTC))

    report = _sync(client)

    assert (report["alerts"], report["waiting"], report["offer_ids"]) == (1, 1, [])
    assert client.get("/api/mail/status").json()["waiting"] == 1


def test_another_senders_alert_is_read_by_the_model_then_scored(
    client: TestClient, mailbox: Mailbox, alert_folder: str
):
    fake = FakeLLMClient()
    client.app.state.llm_client = fake  # type: ignore[attr-defined]
    current = client.get("/api/cv/fr").json()
    client.put(
        "/api/cv/fr",
        json={"draft": {"mode": "text", "text": CV}, "expected_sha256": current["sha256"]},
    )
    mailbox.append(alert_folder, _other_alert(), datetime.now(UTC))
    lead = ExtractedOffer(
        title="Tech Lead", company_name="Voltéo", locations=["Lyon"], contract="CDI"
    )
    fake.queue("extract_offer", ExtractOfferOutput(offers=[lead]))
    fake.queue(
        "score_offer",
        ScoreOfferOutput(mission=7, stack=8, salary=5, culture=6, strengths=[], summary="Bien."),
    )

    report = _sync(client)

    assert (report["waiting"], report["unscored_ids"], report["error"]) == (0, [], None)
    [offer] = client.get("/api/offers").json()
    assert offer["state"] == "scored"
    assert offer["message_id"] is not None
    assert offer["llm_call_id"] is not None
    assert client.get("/api/mail/status").json()["waiting"] == 0


def test_an_unreachable_mailbox_is_said_and_nothing_stored(
    client: TestClient, settings: Settings, no_model: None
):
    client.app.state.settings = settings.model_copy(update={"mail_imap_port": 1})  # type: ignore[attr-defined]

    response = client.post("/api/mail/sync")

    assert response.status_code == 502
    assert "injoignable" in response.json()["message"]
    assert client.get("/api/mail/messages").json() == []


def test_the_status_says_which_mailbox_is_read(
    client: TestClient, mailbox: Mailbox, no_model: None
):
    before = client.get("/api/mail/status").json()
    assert before["address"] == mailbox.address
    assert before["local"] is True
    assert before["dry_run"] is True
    assert before["folders"] == [{"folder": "INBOX", "synced_at": None}]

    mailbox.deliver(_recruiter())
    _sync(client)

    assert client.get("/api/mail/status").json()["folders"][0]["synced_at"] is not None


def test_an_unknown_message_is_not_found(client: TestClient):
    assert client.get("/api/mail/messages/999999").status_code == 404


# --- classifying and matching ----------------------------------------------------

from jobingo.llm.client import LLMValidationError, Usage  # noqa: E402
from jobingo.llm.tasks.classify_message import ClassifyMessageOutput  # noqa: E402


@pytest.fixture
def fake(client: TestClient) -> FakeLLMClient:
    model = FakeLLMClient()
    client.app.state.llm_client = model  # type: ignore[attr-defined]
    return model


def _classified(category: str, company: str = "", on: str | None = None) -> ClassifyMessageOutput:
    return ClassifyMessageOutput(
        category=category,  # type: ignore[arg-type]
        company_name=company,
        interview_date=on,
        summary="Une phrase.",
    )


def _from(sender: str, subject: str, body: str = "Bonjour.", **headers: str) -> EmailMessage:
    message = _mail(From=sender, Subject=subject, **headers)
    message.set_content(body)
    return message


def _application(client: TestClient, company: str = "Voltéo", contact: str = "") -> int:
    app_id = client.post(
        "/api/applications", json={"title": "Data engineer", "company_name": company}
    ).json()["id"]
    if contact:
        client.put(f"/api/applications/{app_id}/contact", json={"email": contact})
    return app_id


def _only(client: TestClient, hidden: bool = False) -> Any:
    [message] = client.get("/api/mail/messages", params={"hidden": hidden}).json()
    return client.get(f"/api/mail/messages/{message['id']}").json()


def test_a_newsletter_is_hidden_without_the_model(
    client: TestClient, mailbox: Mailbox, fake: FakeLLMClient
):
    mailbox.deliver(
        _from("Lettre <news@reseau.test>", "Les nouvelles", List_Unsubscribe="<https://x.test>")
    )

    report = _sync(client)

    assert (report["hidden"], report["classified"], report["waiting"]) == (1, 0, 0)
    assert fake.prompts == []
    assert client.get("/api/mail/messages").json() == []
    hidden = _only(client, hidden=True)
    assert (hidden["hidden_reason"], hidden["category"]) == ("newsletter", None)


def test_a_restored_newsletter_goes_to_the_model_at_the_next_sync(
    client: TestClient, mailbox: Mailbox, fake: FakeLLMClient
):
    mailbox.deliver(
        _from("Alertes <alertes@emplois.test>", "Offres", List_Unsubscribe="<https://x.test>")
    )
    _sync(client)
    message_id = _only(client, hidden=True)["id"]

    restored = client.put(f"/api/mail/messages/{message_id}/hidden", json={"hidden": False})
    assert restored.json()["hidden_reason"] is None
    fake.queue("classify_message", _classified("recruiter_other"))
    report = _sync(client)

    assert report["classified"] == 1
    assert _only(client)["category"] == "recruiter_other"


def test_a_rejection_is_tied_to_its_application_and_suggests_closing_it(
    client: TestClient, mailbox: Mailbox, fake: FakeLLMClient
):
    app_id = _application(client, "Voltéo SAS")
    mailbox.deliver(_from("rh@volteo.test", "Votre candidature", "Nous ne donnerons pas suite."))
    fake.queue("classify_message", _classified("rejection", company="Voltéo"))

    report = _sync(client)

    assert (report["classified"], report["linked"]) == (1, 1)
    message = _only(client)
    assert (message["application_id"], message["linked_by"]) == (app_id, "match")
    assert message["suggestion"]["type"] == "rejected"
    assert message["suggestion"]["status"] == "pending"
    assert message["llm_call_id"] is not None
    application = client.get(f"/api/applications/{app_id}").json()
    # Tied, the message records itself; the refusal waits for a click.
    assert application["status"] == "en_echange"
    assert [m["id"] for m in application["messages"]] == [message["id"]]
    assert client.get("/api/mail/status").json()["suggestions"] == 1

    accepted = client.post(f"/api/mail/messages/{message['id']}/suggestion/accept")

    assert accepted.json()["suggestion"]["status"] == "accepted"
    application = client.get(f"/api/applications/{app_id}").json()
    assert application["status"] == "cloture"
    assert {e["message_id"] for e in application["events"]} == {message["id"]}
    again = client.post(f"/api/mail/messages/{message['id']}/suggestion/accept")
    assert again.status_code == 409


def test_an_interview_is_dated_from_the_message(
    client: TestClient, mailbox: Mailbox, fake: FakeLLMClient
):
    app_id = _application(client, contact="camille@volteo.test")
    mailbox.deliver(_from("Camille Roux <camille@volteo.test>", "Entretien"))
    fake.queue("classify_message", _classified("interview", on="2026-11-20"))

    _sync(client)
    message = _only(client)
    assert message["application_id"] == app_id  # by the contact's address
    client.post(f"/api/mail/messages/{message['id']}/suggestion/accept")

    events = client.get(f"/api/applications/{app_id}").json()["events"]
    assert [(e["type"], e["occurred_at"]) for e in events][0] == (
        "interview_scheduled",
        "2026-11-20",
    )


def test_a_reply_in_a_thread_follows_the_first_message(
    client: TestClient, mailbox: Mailbox, fake: FakeLLMClient
):
    app_id = _application(client)
    first = _from("rh@inconnu.test", "Votre candidature", Message_ID="<t1@inconnu.test>")
    mailbox.deliver(first)
    fake.queue("classify_message", _classified("recruiter_other"))
    _sync(client)
    [message] = client.get("/api/mail/messages").json()
    client.put(f"/api/mail/messages/{message['id']}/application", json={"application_id": app_id})

    mailbox.deliver(
        _from(
            "rh@inconnu.test",
            "Re: Votre candidature",
            Message_ID="<t2@inconnu.test>",
            In_Reply_To="<t1@inconnu.test>",
            References="<t1@inconnu.test>",
        )
    )
    fake.queue("classify_message", _classified("recruiter_other"))
    report = _sync(client)

    assert report["linked"] == 1
    linked = client.get(f"/api/applications/{app_id}").json()["messages"]
    assert len(linked) == 2


def test_an_unmatched_suggestion_needs_an_application_first(
    client: TestClient, mailbox: Mailbox, fake: FakeLLMClient
):
    mailbox.deliver(_from("rh@inconnu.test", "Votre candidature"))
    fake.queue("classify_message", _classified("rejection", company="Inconnue"))
    _sync(client)
    message = _only(client)
    assert message["application_id"] is None

    refused = client.post(f"/api/mail/messages/{message['id']}/suggestion/accept")
    assert refused.status_code == 409
    assert "Rattachez" in refused.json()["message"]
    dismissed = client.post(f"/api/mail/messages/{message['id']}/suggestion/dismiss")
    assert dismissed.json()["suggestion"]["status"] == "dismissed"


def test_moving_a_message_moves_its_events_and_untying_removes_them(
    client: TestClient, mailbox: Mailbox, fake: FakeLLMClient
):
    first, second = _application(client, "Voltéo"), _application(client, "Plume Énergie")
    mailbox.deliver(_from("rh@volteo.test", "Votre candidature"))
    fake.queue("classify_message", _classified("rejection", company="Voltéo"))
    _sync(client)
    message_id = _only(client)["id"]
    client.post(f"/api/mail/messages/{message_id}/suggestion/accept")
    url = f"/api/mail/messages/{message_id}/application"

    moved = client.put(url, json={"application_id": second}).json()

    assert (moved["application_id"], moved["linked_by"]) == (second, "user")
    assert client.get(f"/api/applications/{first}").json()["status"] == "a_postuler"
    assert client.get(f"/api/applications/{second}").json()["status"] == "cloture"

    untied = client.put(url, json={"application_id": None}).json()

    assert untied["suggestion"]["status"] == "pending"  # to decide again, once tied
    assert client.get(f"/api/applications/{second}").json()["events"] == []
    assert client.put(url, json={"application_id": 999999}).status_code == 404


def test_a_job_described_in_a_message_becomes_an_offer(
    client: TestClient, mailbox: Mailbox, fake: FakeLLMClient
):
    mailbox.deliver(
        _from("Camille Roux <camille@cabinet.test>", "Poste", "Je recrute un Tech Lead.")
    )
    fake.queue("classify_message", _classified("offer"))
    fake.queue(
        "extract_offer",
        ExtractOfferOutput(offers=[ExtractedOffer(title="Tech Lead", company_name="Voltéo")]),
    )
    fake.queue(
        "score_offer",
        ScoreOfferOutput(mission=7, stack=8, salary=5, culture=6, strengths=[], summary="Bien."),
    )

    report = _sync(client)

    assert len(report["offer_ids"]) == 1
    message = _only(client)
    assert message["offer_ids"] == report["offer_ids"]
    assert message["application_id"] is None  # a new job, not news of an application


def test_what_the_model_files_as_other_is_hidden(
    client: TestClient, mailbox: Mailbox, fake: FakeLLMClient
):
    mailbox.deliver(_from("ami@exemple.test", "Dimanche"))
    fake.queue("classify_message", _classified("other"))

    _sync(client)

    assert client.get("/api/mail/messages").json() == []
    assert _only(client, hidden=True)["hidden_reason"] == "other"


def test_a_blocked_sender_never_reaches_the_model_again(
    client: TestClient, mailbox: Mailbox, fake: FakeLLMClient
):
    mailbox.deliver(_from("Promo <promo@boutique.test>", "Soldes"))
    fake.queue("classify_message", _classified("recruiter_other"))
    _sync(client)
    message_id = _only(client)["id"]

    blocked = client.post(f"/api/mail/messages/{message_id}/block-sender").json()
    assert blocked["hidden_reason"] == "blocked_sender"
    mailbox.deliver(_from("promo@boutique.test", "Encore des soldes"))
    report = _sync(client)

    assert (report["hidden"], report["classified"]) == (1, 0)
    assert len(fake.prompts) == 1
    client.put(f"/api/mail/messages/{message_id}/hidden", json={"hidden": False})
    mailbox.deliver(_from("promo@boutique.test", "Dernières soldes"))
    fake.queue("classify_message", _classified("other"))
    assert _sync(client)["classified"] == 1  # restoring unblocked the sender


def test_a_failed_classification_waits_for_the_next_sync(
    client: TestClient, mailbox: Mailbox, fake: FakeLLMClient
):
    mailbox.deliver(_from("rh@volteo.test", "Votre candidature"))
    fake.queue(
        "classify_message",
        LLMValidationError("bad", model=fake.model, usage=Usage(attempts=1), request={}),
    )

    report = _sync(client)

    assert report["waiting"] == 1
    assert "classer" in report["error"]
    assert _only(client)["category"] is None
    fake.queue("classify_message", _classified("recruiter_other"))
    assert _sync(client)["classified"] == 1
    assert client.get("/api/mail/status").json()["waiting"] == 0


def test_the_candidate_is_redacted_from_the_message(
    client: TestClient, mailbox: Mailbox, fake: FakeLLMClient
):
    client.put(
        "/api/identity",
        json={
            "name": "Alex Moreau",
            "email": "alex@example.org",
            "phone": "",
            "address": "",
            "linkedin": "",
            "github": "",
        },
    )
    mailbox.deliver(_from("rh@volteo.test", "Entretien", "Bonjour Alex Moreau, êtes-vous libre ?"))
    fake.queue("classify_message", _classified("interview"))

    _sync(client)

    [(task, prompt)] = fake.prompts
    assert task == "classify_message"
    assert "Alex" not in prompt.user
    assert "[CANDIDAT]" in prompt.user

"""The approval queue and its one executor. Real sends go to the local Mailpit (`make
mail-up`), read back through its API; each test writes to its own address."""

import json
import time
import urllib.parse
import urllib.request
from email import message_from_bytes, policy
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from jobingo.config import Settings
from jobingo.db import Conn
from jobingo.render.pdf import engine_available

needs_engine = pytest.mark.skipif(not engine_available(), reason="WeasyPrint needs Pango")
CV = (Path(__file__).parent / "fixtures" / "cv.fr.md").read_text(encoding="utf-8")
MAILPIT = "http://127.0.0.1:8025/api/v1"


def _mailpit(path: str) -> Any:
    with urllib.request.urlopen(f"{MAILPIT}/{path}", timeout=5) as response:  # noqa: S310
        return json.load(response)


def _received(address: str, expected: int = 1) -> list[dict[str, Any]]:
    """What Mailpit holds for `address`, waiting a moment for it to arrive."""
    query = urllib.parse.quote(f"to:{address}")
    messages: list[dict[str, Any]] = []
    for _ in range(50):
        messages = _mailpit(f"search?query={query}")["messages"]
        if len(messages) >= expected:
            break
        time.sleep(0.05)
    return messages


@pytest.fixture
def recipient() -> str:
    try:
        _mailpit("info")
    except OSError as error:
        pytest.fail(f"Mailpit is unreachable, run `make mail-up`: {error}")
    return f"camille-{uuid4().hex[:10]}@volteo.test"


@pytest.fixture
def sending(client: TestClient, settings: Settings) -> Settings:
    """Dry run off: the local Mailpit receives what leaves."""
    live = settings.model_copy(update={"smtp_dry_run": False})
    client.app.state.settings = live  # type: ignore[attr-defined]
    return live


@pytest.fixture
def application(client: TestClient) -> int:
    client.put(
        "/api/identity",
        json={
            "name": "Alex Moreau",
            "email": "alex@jobingo.test",
            "phone": "",
            "address": "",
            "linkedin": "",
            "github": "",
        },
    )
    return client.post(
        "/api/applications", json={"title": "Data engineer", "company_name": "Voltéo"}
    ).json()["id"]


def _propose(client: TestClient, to: str, **extra: Any) -> Any:
    body = {"to": [to], "subject": "Ma candidature", "body": "Bonjour,\n\nVoici.\n"} | extra
    response = client.post("/api/actions", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _approve(client: TestClient, action: Any) -> Any:
    return client.post(
        f"/api/actions/{action['id']}/approve", json={"payload_hash": action["payload_hash"]}
    )


def test_a_proposal_waits_for_a_click_and_sends_nothing(
    client: TestClient, recipient: str, application: int
):
    action = _propose(client, recipient, application_id=application)

    assert action["status"] == "proposed"
    assert action["payload"]["from_name"] == "Alex Moreau"  # put in by code
    assert action["payload"]["body_text"] == "Bonjour,\n\nVoici.\n"
    assert client.get("/api/actions").json()[0]["id"] == action["id"]
    assert _received(recipient, expected=0) == []


def test_a_bad_address_is_refused(client: TestClient):
    response = client.post(
        "/api/actions", json={"to": ["pas une adresse"], "subject": "x", "body": "y"}
    )
    assert response.status_code == 422
    assert "Adresse invalide" in response.json()["message"]


def test_approving_another_payload_than_the_one_shown_is_refused(
    client: TestClient, recipient: str
):
    action = _propose(client, recipient)

    response = client.post(f"/api/actions/{action['id']}/approve", json={"payload_hash": "0" * 64})

    assert response.status_code == 409
    assert "aperçu" in response.json()["message"]
    assert client.get(f"/api/actions/{action['id']}").json()["status"] == "proposed"


def test_a_dry_run_builds_the_message_and_sends_nothing(
    client: TestClient, recipient: str, application: int
):
    action = _propose(client, recipient, application_id=application)

    done = _approve(client, action).json()

    assert (done["status"], done["dry_run"]) == ("sent", True)
    assert _received(recipient, expected=0) == []
    # Nothing left, so nothing is recorded as sent on the application.
    assert client.get(f"/api/applications/{application}").json()["events"] == []
    eml = client.get(f"/api/actions/{action['id']}/eml")
    built = message_from_bytes(eml.content, policy=policy.default)
    assert built["From"] == "Alex Moreau <alex@jobingo.test>"
    assert built["Message-ID"] == action["payload"]["message_id"]


def test_an_approved_send_leaves_once_and_is_recorded(
    client: TestClient, recipient: str, application: int, sending: Settings
):
    action = _propose(client, recipient, application_id=application)

    done = _approve(client, action).json()
    again = _approve(client, action)

    assert (done["status"], done["dry_run"]) == ("sent", False)
    assert again.status_code == 409  # a second click sends nothing
    [received] = _received(recipient)
    assert received["Subject"] == "Ma candidature"
    assert received["MessageID"] == action["payload"]["message_id"].strip("<>")
    application_view = client.get(f"/api/applications/{application}").json()
    assert application_view["status"] == "en_echange"
    [sent] = application_view["events"]
    assert (sent["type"], sent["action_id"]) == ("message_sent", action["id"])


def test_a_failed_send_is_kept_and_retried_with_the_same_message_id(
    client: TestClient, recipient: str, sending: Settings
):
    client.app.state.settings = sending.model_copy(update={"mail_smtp_port": 1})  # type: ignore[attr-defined]
    action = _propose(client, recipient)

    failed = _approve(client, action).json()

    assert failed["status"] == "failed"
    assert "SMTP" in failed["error"]
    client.app.state.settings = sending  # type: ignore[attr-defined]
    retried = client.post(f"/api/actions/{action['id']}/retry").json()
    assert retried["status"] == "sent"
    [received] = _received(recipient)
    assert received["MessageID"] == action["payload"]["message_id"].strip("<>")


def test_a_payload_changed_after_approval_is_not_sent(
    client: TestClient, conn: Conn, recipient: str, sending: Settings
):
    action = _propose(client, recipient)
    conn.execute(
        "UPDATE pending_actions SET status = 'approved', approved_hash = %s WHERE id = %s",
        ("f" * 64, action["id"]),
    )

    failed = client.post(f"/api/actions/{action['id']}/retry")

    assert failed.status_code == 409  # only a failed send is retried
    with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
        conn.execute(
            "UPDATE pending_actions SET payload = '{}'::jsonb WHERE id = %s", (action["id"],)
        )
    with pytest.raises(psycopg.errors.RaiseException, match="never deleted"):
        conn.execute("DELETE FROM pending_actions WHERE id = %s", (action["id"],))


def test_the_executor_checks_the_approved_hash(
    client: TestClient, conn: Conn, recipient: str, sending: Settings
):
    """The second line of defence: an approval recorded for other content sends nothing."""
    from jobingo.hitl.executor import execute

    action = _propose(client, recipient)
    user_id = conn.execute("SELECT user_id FROM pending_actions WHERE id = %s", (action["id"],))
    owner = user_id.fetchone()
    assert owner is not None
    conn.execute(
        "UPDATE pending_actions SET status = 'approved', approved_hash = %s WHERE id = %s",
        ("f" * 64, action["id"]),
    )

    result = execute(conn, sending, owner["user_id"], action["id"])

    assert result is not None
    assert result.status == "failed"
    assert result.error is not None and "approbation" in result.error
    assert _received(recipient, expected=0) == []


def test_a_rejected_proposal_stays_in_the_record(client: TestClient, recipient: str):
    action = _propose(client, recipient)

    rejected = client.post(f"/api/actions/{action['id']}/reject").json()

    assert rejected["status"] == "rejected"
    assert _approve(client, action).status_code == 409
    assert client.post(f"/api/actions/{action['id']}/reject").status_code == 409


def test_an_attachment_needs_an_application(client: TestClient, recipient: str):
    response = client.post(
        "/api/actions",
        json={"to": [recipient], "subject": "x", "body": "y", "attachments": [{"kind": "cv"}]},
    )
    assert response.status_code == 422
    assert "candidature" in response.json()["message"]


@needs_engine
def test_the_cv_is_archived_once_and_sent_as_archived(
    client: TestClient, conn: Conn, recipient: str, application: int, sending: Settings
):
    current = client.get("/api/cv/fr").json()
    client.put(
        "/api/cv/fr",
        json={"draft": {"mode": "text", "text": CV}, "expected_sha256": current["sha256"]},
    )
    action = _propose(client, recipient, application_id=application, attachments=[{"kind": "cv"}])
    [attachment] = action["payload"]["attachments"]
    archived = client.get(f"/api/documents/{attachment['document_id']}/pdf")
    assert archived.headers["content-type"] == "application/pdf"

    _approve(client, action)

    [received] = _received(recipient)
    detail = _mailpit(f"message/{received['ID']}")
    [part] = detail["Attachments"]
    assert part["FileName"] == attachment["filename"]
    assert part["Size"] == len(archived.content)
    with pytest.raises(psycopg.errors.RaiseException, match="archived"):
        conn.execute(
            "UPDATE documents SET content = 'x' WHERE id = %s", (attachment["document_id"],)
        )


def test_a_reply_answers_its_message_in_its_thread(
    client: TestClient, conn: Conn, recipient: str, application: int, sending: Settings
):
    user = conn.execute("SELECT id FROM users").fetchone()
    assert user is not None
    row = conn.execute(
        """
        INSERT INTO messages (user_id, mailbox, folder, message_id, thread_id, in_reply_to,
            from_addr, to_addrs, subject, body_text, body_html, list_unsubscribe, received_at,
            kind, application_id)
        VALUES (%s, 'alex@jobingo.test', 'INBOX', '<r2@volteo.test>', '<r1@volteo.test>',
            '<r1@volteo.test>', %s, 'alex@jobingo.test', 'Entretien', 'Jeudi ?', '', false,
            now(), 'message', %s)
        RETURNING id
        """,
        (user["id"], recipient, application),
    ).fetchone()
    assert row is not None

    action = _propose(client, recipient, message_id=row["id"], subject="Re: Entretien")

    assert action["application_id"] == application  # from the message
    _approve(client, action)
    [received] = _received(recipient)
    headers = _mailpit(f"message/{received['ID']}/headers")
    assert headers["In-Reply-To"] == ["<r2@volteo.test>"]
    assert headers["References"] == ["<r1@volteo.test> <r2@volteo.test>"]

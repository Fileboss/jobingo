"""Drafting replies: the model writes, code flags what to check, the queue refuses any
gap left, and nothing leaves without the approval click."""

import json
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from jobingo.db import Conn
from jobingo.domain.placeholders import PLACEHOLDER_LABELS, find_placeholders
from jobingo.domain.reply import reply_warnings
from jobingo.domain.style import StyleGuide
from jobingo.llm.fake import FakeLLMClient
from jobingo.llm.prompts import PROMPTS
from jobingo.llm.tasks.draft_reply import DraftReplyOutput

ROOT = Path(__file__).resolve().parent.parent


# --- gaps and warnings, in code ----------------------------------------------------


def test_the_canonical_marker_and_every_other_gap_are_found():
    found = find_placeholders(
        "Je suis libre [à compléter : Disponibilités], le XX/XX, chez {{entreprise}} "
        "et [CANDIDAT] signe ___ ; voir [le site](https://x.test)."
    )
    assert [(p.text, p.label) for p in found] == [
        ("[à compléter : Disponibilités]", "disponibilités"),
        ("XX/XX", None),
        ("{{entreprise}}", None),
        ("[CANDIDAT]", None),
        ("___", None),
    ]
    assert find_placeholders("Écrivez-moi à <rh@volteo.test>.") == []


def test_a_draft_is_flagged_not_blocked():
    style = StyleGuide(forbidden=["n'hésitez pas à"])
    warnings = reply_warnings(
        "N'hésitez pas à me rappeler le 14. Je suis libre [À COMPLÉTER : date].",
        style,
        sources="Pouvons-nous nous voir ?",
    )
    assert warnings[0].startswith("tournure interdite")
    assert warnings[1] == "nombre absent du message et de la consigne : 14"
    assert "à compléter avant l'envoi" in warnings[2]


def test_the_prompt_lists_the_labels_the_code_recognises():
    system = (ROOT / "packages/core/src/jobingo/llm/prompts/draft_reply.v4.system.md").read_text(
        encoding="utf-8"
    )
    assert ", ".join(PLACEHOLDER_LABELS) + "." in " ".join(system.split())


def test_no_prompt_example_is_an_eval_case():
    """An example in the prompt would make its eval case a question with the answer
    given: the score would measure nothing."""
    cases = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "evals/cases").glob("*.jsonl")
    )
    folded = " ".join(cases.split()).casefold()
    prompts = ROOT / "packages/core/src/jobingo/llm/prompts"
    examples = [
        " ".join(text.split()).casefold()
        for path in prompts.glob("*.md")
        for text in re.findall(r"<entree>(.*?)</entree>", path.read_text(encoding="utf-8"), re.S)
    ]
    assert examples, "the prompts have examples: this test must see them"
    for example in examples:
        # Every sentence of an example quoting a message, checked on its own.
        for quoted in re.findall(r"« (.{20,}?) »", example):
            assert quoted not in folded, f"prompt example used as an eval case: {quoted!r}"
    assert PROMPTS is not None


# --- the API -------------------------------------------------------------------------


@pytest.fixture
def fake(client: TestClient) -> FakeLLMClient:
    model = FakeLLMClient()
    client.app.state.llm_client = model  # type: ignore[attr-defined]
    return model


@pytest.fixture
def message_id(client: TestClient, conn: Conn) -> int:
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
    user = conn.execute("SELECT id FROM users").fetchone()
    assert user is not None
    row = conn.execute(
        """
        INSERT INTO messages (user_id, mailbox, folder, message_id, thread_id, in_reply_to,
            from_addr, to_addrs, subject, body_text, body_html, list_unsubscribe, received_at,
            kind, processed_at)
        VALUES (%s, 'alex@jobingo.test', 'INBOX', '<m1@volteo.test>', '<m1@volteo.test>', '',
            'Camille Roux <camille@volteo.test>', 'alex@jobingo.test', 'Entretien',
            'Bonjour Alex Moreau, quelles sont vos disponibilités ?', '', false, now(),
            'message', now())
        RETURNING id
        """,
        (user["id"],),
    ).fetchone()
    assert row is not None
    return row["id"]


def _draft(client: TestClient, message_id: int, **request: Any) -> Any:
    body = {"intent": "accepter_entretien"} | request
    return client.post(f"/api/mail/messages/{message_id}/reply-draft", json=body)


def test_a_draft_comes_with_its_call_and_what_to_check(
    client: TestClient, fake: FakeLLMClient, message_id: int
):
    fake.queue(
        "draft_reply",
        DraftReplyOutput(
            subject="Re : Entretien",
            body="Bonjour,\n\nJe suis disponible [À COMPLÉTER : disponibilités].\n\nCordialement,",
            notes="Indiquez vos disponibilités.",
        ),
    )

    draft = _draft(client, message_id, instruction="Plutôt le matin.").json()

    assert draft["llm_call_id"] is not None
    assert draft["notes"] == "Indiquez vos disponibilités."
    assert any("à compléter" in w for w in draft["warnings"])
    [(task, prompt)] = fake.prompts
    assert task == "draft_reply"
    assert "Alex" not in prompt.user  # redacted
    assert "[CANDIDAT]" in prompt.user
    assert "Plutôt le matin." in prompt.user
    assert client.get("/api/actions").json() == []  # a draft queues nothing


def test_a_gap_left_in_the_text_cannot_be_queued(
    client: TestClient, fake: FakeLLMClient, message_id: int
):
    fake.queue("draft_reply", DraftReplyOutput(subject="Re : Entretien", body="Libre [date]."))
    draft = _draft(client, message_id).json()
    proposal = {
        "message_id": message_id,
        "to": ["camille@volteo.test"],
        "subject": draft["subject"],
        "body": draft["body"],
        "llm_call_id": draft["llm_call_id"],
    }

    refused = client.post("/api/actions", json=proposal)
    assert refused.status_code == 422
    assert "« [date] »" in refused.json()["message"]

    edited = client.post("/api/actions", json=proposal | {"body": "Libre jeudi matin."})
    assert edited.status_code == 201
    assert edited.json()["llm_call_id"] == draft["llm_call_id"]


def test_no_draft_without_a_model_or_a_message(client: TestClient, message_id: int):
    client.app.state.llm_client = None  # type: ignore[attr-defined]
    assert _draft(client, message_id).status_code == 503
    client.app.state.llm_client = FakeLLMClient()  # type: ignore[attr-defined]
    assert _draft(client, 999999).status_code == 404
    assert _draft(client, message_id, intent="pirater").status_code == 422


def test_the_reply_cases_are_fictional():
    for name in ("draft_reply", "injection"):
        text = (ROOT / f"evals/cases/{name}.jsonl").read_text(encoding="utf-8")
        assert not re.search(r"@[\w.-]+\.(fr|com|io)\b", text), name
        for line in text.splitlines():
            if line.strip() and not line.startswith("//"):
                json.loads(line)

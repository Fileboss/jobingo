"""`run_task`, the one way to call the model: every call is journalled with its real
cost, the budget is checked first, and the candidate's identity never reaches a prompt."""

import logging
from datetime import date, timedelta
from decimal import Decimal

import pytest
from jinja2 import DictLoader
from pydantic import BaseModel

from jobingo.db import Conn
from jobingo.domain.identity import Identity
from jobingo.llm.client import LLMUnavailable, LLMValidationError, Task, UntrustedText, Usage
from jobingo.llm.fake import FakeLLMClient
from jobingo.llm.journal import Budget, LLMBudgetExceeded, run_task
from jobingo.llm.prompts import prompt_environment
from jobingo.services.accounts import ensure_account
from jobingo.services.identity import redaction_values, save_identity


class Mail(BaseModel):
    body: UntrustedText


class Verdict(BaseModel):
    kind: str


PROMPTS = prompt_environment(
    DictLoader(
        {"sort.system.md": "Trie ce courriel.", "sort.md": "<mail>{{ payload.body }}</mail>"}
    )
)
SORT = Task(
    name="sort",
    tier="fast",
    input_model=Mail,
    output_model=Verdict,
    user_template="sort.md",
    system_template="sort.system.md",
    prompt_version=2,
    prompts=PROMPTS,
)
BUDGET = Budget(daily_usd=Decimal(1), monthly_usd=Decimal(10))
USAGE = Usage(input_tokens=1000, output_tokens=200, cache_read_tokens=4000, attempts=1)


@pytest.fixture
def user_id(conn: Conn) -> int:
    return ensure_account(conn, "alex").id


def _calls(conn: Conn) -> list[dict[str, object]]:
    return list(conn.execute("SELECT * FROM llm_calls ORDER BY id"))


def test_a_call_is_journalled_with_its_cost_and_returns_its_id(conn: Conn, user_id: int):
    client = FakeLLMClient(usage=USAGE)
    client.queue("sort", Verdict(kind="offre"))

    output, call_id = run_task(
        conn, client, BUDGET, user_id, SORT, Mail(body="Bonjour"), redaction_values=[]
    )

    assert output == Verdict(kind="offre")
    [row] = _calls(conn)
    assert row["id"] == call_id
    assert row["user_id"] == user_id
    assert (row["task"], row["prompt_version"], row["status"]) == ("sort", 2, "ok")
    assert row["model"] == "claude-haiku-5-5"
    assert (row["input_tokens"], row["output_tokens"], row["cache_read_tokens"]) == (
        1000,
        200,
        4000,
    )
    # 1000 × 0.10 + 4000 × 0.01 + 200 × 0.50, per million tokens
    assert row["cost_usd"] == Decimal("0.00024")
    assert row["response"] == {"kind": "offre"}
    assert row["request"] == {
        "model": "claude-haiku-5-5",
        "system": "Trie ce courriel.",
        "user": "<mail>Bonjour</mail>",
    }


@pytest.mark.parametrize(
    ("error", "status"), [(LLMValidationError, "failed"), (LLMUnavailable, "error")]
)
def test_a_failed_call_is_journalled_with_what_it_cost(
    conn: Conn, user_id: int, error: type[LLMValidationError | LLMUnavailable], status: str
):
    client = FakeLLMClient()
    spent = Usage(input_tokens=2000, output_tokens=400, attempts=2)
    client.queue("sort", error("bad", model="claude-haiku-5-5", usage=spent, request={"x": 1}))

    with pytest.raises(error):
        run_task(conn, client, BUDGET, user_id, SORT, Mail(body="Bonjour"), redaction_values=[])

    [row] = _calls(conn)
    assert (row["status"], row["error"], row["attempts"]) == (status, "bad", 2)
    assert row["cost_usd"] == Decimal("0.0004")
    assert row["response"] is None


def test_the_candidate_identity_never_reaches_the_prompt_or_the_journal(conn: Conn, user_id: int):
    save_identity(
        conn,
        user_id,
        Identity(name="Alex Moreau", email="alex.moreau@example.org", phone="06 12 34 56 78"),
    )
    client = FakeLLMClient()
    client.queue("sort", Verdict(kind="recruteur"))
    mail = Mail(
        body="Bonjour Alex Moreau, joignable au +33 6 12 34 56 78 ou alex.moreau@example.org ?"
    )

    run_task(
        conn,
        client,
        BUDGET,
        user_id,
        SORT,
        mail,
        redaction_values=redaction_values(conn, user_id),
    )

    [(_, prompt)] = client.prompts
    assert prompt.user == "<mail>Bonjour [CANDIDAT], joignable au [CANDIDAT] ou [CANDIDAT] ?</mail>"
    [row] = _calls(conn)
    journalled = str(row["request"])
    for value in ("Alex", "Moreau", "alex.moreau", "12 34"):
        assert value not in journalled


def test_the_daily_cap_stops_calls_before_anything_is_sent(conn: Conn, user_id: int):
    client = FakeLLMClient(usage=Usage(input_tokens=0, output_tokens=2_000_000, attempts=1))
    client.queue("sort", Verdict(kind="offre"))
    client.queue("sort", Verdict(kind="offre"))
    run_task(conn, client, BUDGET, user_id, SORT, Mail(body="1"), redaction_values=[])

    with pytest.raises(LLMBudgetExceeded, match="quotidien"):
        run_task(conn, client, BUDGET, user_id, SORT, Mail(body="2"), redaction_values=[])
    assert len(client.prompts) == 1
    assert len(_calls(conn)) == 1


def test_failed_calls_count_against_the_cap(conn: Conn, user_id: int):
    client = FakeLLMClient()
    spent = Usage(output_tokens=2_000_000, attempts=2)
    client.queue(
        "sort", LLMValidationError("bad", model="claude-haiku-5-5", usage=spent, request={})
    )
    with pytest.raises(LLMValidationError):
        run_task(conn, client, BUDGET, user_id, SORT, Mail(body="1"), redaction_values=[])

    with pytest.raises(LLMBudgetExceeded):
        run_task(conn, client, BUDGET, user_id, SORT, Mail(body="2"), redaction_values=[])


def test_the_monthly_cap_counts_earlier_days_and_the_caps_are_per_user(conn: Conn, user_id: int):
    client = FakeLLMClient(usage=Usage(output_tokens=20_000_000, attempts=1))
    client.queue("sort", Verdict(kind="offre"))
    run_task(conn, client, BUDGET, user_id, SORT, Mail(body="1"), redaction_values=[])
    # Yesterday, unless today is the 1st: the call then stays in this month, today.
    conn.execute(
        "UPDATE llm_calls SET created_at = greatest(created_at - %s, date_trunc('month', now()))",
        (timedelta(days=1),),
    )
    expected = "quotidien" if date.today().day == 1 else "mensuel"

    with pytest.raises(LLMBudgetExceeded, match=expected):
        run_task(conn, client, BUDGET, user_id, SORT, Mail(body="2"), redaction_values=[])

    other = ensure_account(conn, "someone-else").id
    client.queue("sort", Verdict(kind="offre"))
    run_task(conn, client, BUDGET, other, SORT, Mail(body="3"), redaction_values=[])


def test_a_wrong_payload_type_is_refused(conn: Conn, user_id: int):
    with pytest.raises(TypeError):
        run_task(
            conn, FakeLLMClient(), BUDGET, user_id, SORT, Verdict(kind="x"), redaction_values=[]
        )


def test_the_log_event_points_to_the_call_and_holds_no_prompt(
    conn: Conn, user_id: int, caplog: pytest.LogCaptureFixture
):
    client = FakeLLMClient()
    client.queue("sort", Verdict(kind="offre"))
    with caplog.at_level(logging.INFO, logger="jobingo.llm.journal"):
        _, call_id = run_task(
            conn, client, BUDGET, user_id, SORT, Mail(body="Contenu privé"), redaction_values=[]
        )

    [record] = [r for r in caplog.records if r.getMessage() == "llm.call"]
    fields: dict[str, object] = record.__dict__["fields"]
    assert fields["llm_call_id"] == call_id
    assert fields["status"] == "ok"
    assert "Contenu privé" not in caplog.text
    assert "Contenu privé" not in str(fields)

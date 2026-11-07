"""The observability API: every figure is measured from the journal, per account."""

import json
import logging
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jinja2 import DictLoader
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from jobingo.config import Settings
from jobingo.db import Conn
from jobingo.domain.identity import Identity
from jobingo.llm.client import LLMCallError, LLMUnavailable, LLMValidationError, Task, Usage
from jobingo.llm.fake import FakeLLMClient
from jobingo.llm.journal import Budget, run_task
from jobingo.llm.prompts import prompt_environment
from jobingo.llm.tasks import TASKS
from jobingo.llm.tasks.select_cv_content import SELECT_CV_CONTENT_TASK
from jobingo.logs import event
from jobingo.services import app_log
from jobingo.services.accounts import ensure_account, get_account
from jobingo.services.identity import save_identity


class Offer(BaseModel):
    text: str


class Score(BaseModel):
    score: int


PROMPTS = prompt_environment(
    DictLoader({"s.system.md": "Note l'offre.", "s.md": "<offre>{{ payload.text }}</offre>"})
)


def _task(name: str) -> Task[Offer, Score]:
    return Task(
        name=name,
        tier="fast",
        input_model=Offer,
        output_model=Score,
        user_template="s.md",
        system_template="s.system.md",
        prompts=PROMPTS,
    )


SCORE, EXTRACT = _task("score_offer"), _task("extract_offer")
BUDGET = Budget(daily_usd=Decimal(100), monthly_usd=Decimal(1000))

type Call = Callable[..., int | None]


@pytest.fixture
def user_id(client: TestClient, conn: Conn, settings: Settings) -> int:
    account = get_account(conn, settings.account_username)
    assert account is not None
    return account.id


@pytest.fixture
def call(conn: Conn, user_id: int) -> Call:
    """Runs one call through the journal, answered or failed as asked."""

    def run(
        task: Task[Offer, Score] = SCORE,
        *,
        answer: Score | LLMCallError | None = None,
        latency_ms: int = 100,
        attempts: int = 1,
        owner: int | None = None,
        text: str = "Développeuse Python",
    ) -> int | None:
        usage = Usage(
            input_tokens=1000,
            output_tokens=200,
            cache_read_tokens=3000,
            latency_ms=latency_ms,
            attempts=attempts,
        )
        fake = FakeLLMClient(usage=usage)
        fake.queue(task.name, answer or Score(score=4))
        try:
            _, call_id = run_task(
                conn, fake, BUDGET, owner or user_id, task, Offer(text=text), redaction_values=[]
            )
            return call_id
        except (LLMValidationError, LLMUnavailable):
            return None

    return run


def _failure(kind: type[LLMValidationError | LLMUnavailable], latency_ms: int) -> LLMCallError:
    return kind(
        "bad",
        model="claude-haiku-5-5",
        usage=Usage(input_tokens=500, output_tokens=100, latency_ms=latency_ms, attempts=2),
        request={"model": "claude-haiku-5-5"},
    )


def test_usage_sums_every_call_failed_ones_included(client: TestClient, call: Call):
    call(latency_ms=100)
    call(latency_ms=300, attempts=2)
    call(EXTRACT, latency_ms=200)
    # Fails fast: it must not flatter the latency.
    call(answer=_failure(LLMValidationError, 5), latency_ms=5)
    call(answer=_failure(LLMUnavailable, 7))

    report = client.get("/api/observability/usage", params={"days": 7}).json()

    total = report["total"]
    assert (total["calls"], total["ok"], total["failed"], total["errors"]) == (5, 3, 1, 1)
    assert total["retried"] == 3
    assert total["input_tokens"] == 3 * 1000 + 2 * 500
    assert total["cache_read_tokens"] == 3 * 3000
    assert (total["latency_p50_ms"], total["latency_p95_ms"]) == (200, 290)
    # Three answered calls at 0.00023 $ and two failed ones at 0.0001 $.
    assert Decimal(total["cost_usd"]) == Decimal("0.00089")

    by_task = {row["task"]: row for row in report["tasks"]}
    assert by_task["score_offer"]["calls"] == 4
    assert by_task["extract_offer"]["calls"] == 1
    assert report["tasks"][0]["task"] == "score_offer"  # the costliest first

    assert len(report["daily"]) == 7
    assert report["daily"][-1]["calls"] == 5
    assert sum(day["calls"] for day in report["daily"][:-1]) == 0
    assert Decimal(report["budget"]["today_usd"]) == Decimal("0.00089")
    assert report["configured"] is False
    assert [m["model"] for m in report["models"]] == ["claude-haiku-5-5", "claude-sonnet-5-5"]


def test_usage_with_no_call_reports_nothing_measured(client: TestClient):
    report = client.get("/api/observability/usage").json()
    assert report["total"]["calls"] == 0
    assert report["total"]["latency_p50_ms"] is None
    assert report["tasks"] == []
    assert len(report["daily"]) == 30


def test_usage_counts_only_the_period(client: TestClient, call: Call, conn: Conn):
    old = call()
    call()
    conn.execute(
        "UPDATE llm_calls SET created_at = now() - %s WHERE id = %s", (timedelta(days=10), old)
    )
    week = client.get("/api/observability/usage", params={"days": 7}).json()
    month = client.get("/api/observability/usage", params={"days": 30}).json()
    assert (week["total"]["calls"], month["total"]["calls"]) == (1, 2)


def test_calls_are_listed_newest_first_filtered_and_paged(client: TestClient, call: Call):
    first = call()
    call(EXTRACT)
    failed = call(answer=_failure(LLMValidationError, 5))
    last = call()

    page = client.get("/api/observability/calls", params={"limit": 2}).json()
    assert [c["id"] for c in page["calls"]][0] == last
    assert len(page["calls"]) == 2
    assert page["tasks"] == ["extract_offer", "score_offer"]
    rest = client.get(
        "/api/observability/calls", params={"limit": 2, "before_id": page["next_before_id"]}
    ).json()
    assert len(rest["calls"]) == 2 and rest["calls"][-1]["id"] == first
    assert rest["next_before_id"] is None

    failures = client.get("/api/observability/calls", params={"status": "failed"}).json()
    assert [c["status"] for c in failures["calls"]] == ["failed"]
    assert failed is None  # a failed call raises: its id is only in the journal
    extracts = client.get("/api/observability/calls", params={"task": "extract_offer"}).json()
    assert [c["task"] for c in extracts["calls"]] == ["extract_offer"]


def test_a_call_shows_its_prompts_answer_and_the_events_it_caused(
    client: TestClient, call: Call, user_id: int
):
    call_id = call(text="Data engineer à Lyon")
    event(
        logging.getLogger("jobingo.services.offers"),
        "offer.scored",
        user_id=user_id,
        llm_call_id=call_id,
        score=4,
    )

    detail = client.get(f"/api/observability/calls/{call_id}").json()

    assert detail["system_prompt"] == "Note l'offre."
    assert detail["user_prompt"] == "<offre>Data engineer à Lyon</offre>"
    assert detail["parameters"] == {"model": "claude-haiku-5-5"}
    assert detail["answer"] == {"score": 4}
    assert [e["name"] for e in detail["events"]] == ["offer.scored", "llm.call"]
    assert detail["events"][0]["fields"] == {"llm_call_id": call_id, "score": 4}


def test_a_call_of_the_messages_api_shows_its_prompts_and_parsed_answer(
    client: TestClient, conn: Conn, user_id: int
):
    request: dict[str, Any] = {
        "model": "claude-sonnet-5-5",
        "max_tokens": 4000,
        "system": [{"type": "text", "text": "Consignes", "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": "Le courriel"}],
    }
    response = {"content": [{"type": "text", "text": '{"kind": "offre"}'}]}
    row = conn.execute(
        """
        INSERT INTO llm_calls (user_id, task, prompt_version, model, status, input_hash,
            request, response, attempts, input_tokens, output_tokens, cache_read_tokens,
            cache_write_tokens, cost_usd, latency_ms)
        VALUES (%s, 'classify', 1, 'claude-sonnet-5-5', 'ok', 'h', %s, %s, 1, 1, 1, 0, 0, 0, 1)
        RETURNING id
        """,
        (user_id, Jsonb(request), Jsonb(response)),
    ).fetchone()
    assert row is not None

    detail = client.get(f"/api/observability/calls/{row['id']}").json()

    assert detail["system_prompt"] == "Consignes"
    assert detail["user_prompt"] == "Le courriel"
    assert detail["parameters"] == {"model": "claude-sonnet-5-5", "max_tokens": 4000}
    assert detail["answer"] == {"kind": "offre"}


def test_another_accounts_calls_and_events_stay_hidden(client: TestClient, call: Call, conn: Conn):
    other = ensure_account(conn, "someone-else").id
    theirs = call(owner=other)

    assert client.get(f"/api/observability/calls/{theirs}").status_code == 404
    assert client.get("/api/observability/calls").json()["calls"] == []
    assert client.get("/api/observability/usage").json()["total"]["calls"] == 0
    assert client.get("/api/observability/events").json()["events"] == []


def test_events_filter_by_level_and_text(client: TestClient, user_id: int):
    log = logging.getLogger("jobingo.test")
    event(log, "sync.started", user_id=user_id, folder="INBOX")
    event(log, "sync.failed", logging.WARNING, user_id=user_id, reason="imap timeout")
    event(log, "offer.dismissed", user_id=user_id, offer_id=12)
    log.info("a plain line is not stored")

    def names(**params: str) -> list[str]:
        page = client.get("/api/observability/events", params=params).json()
        return [e["name"] for e in page["events"]]

    assert names() == ["offer.dismissed", "sync.failed", "sync.started"]
    assert names(level="WARNING") == ["sync.failed"]
    assert names(q="sync") == ["sync.failed", "sync.started"]
    assert names(q="timeout") == ["sync.failed"]
    assert names(q="100%") == []


def test_a_stored_event_never_holds_the_candidate_identity(
    client: TestClient, conn: Conn, user_id: int
):
    save_identity(conn, user_id, Identity(name="Alex Moreau", email="alex@example.org"))
    event(
        logging.getLogger("jobingo.test"),
        "mail.received",
        user_id=user_id,
        subject="Bonjour Alex Moreau",
        sender={"address": "alex@example.org"},
    )

    [stored] = client.get("/api/observability/events").json()["events"]
    assert stored["fields"] == {
        "subject": "Bonjour [CANDIDAT]",
        "sender": {"address": "[CANDIDAT]"},
    }


def test_prompts_and_events_expire_but_costs_stay(
    client: TestClient, call: Call, conn: Conn, user_id: int
):
    old = call()
    recent = call()
    conn.execute(
        "UPDATE llm_calls SET created_at = now() - %s WHERE id = %s", (timedelta(days=91), old)
    )
    conn.execute(
        "UPDATE app_events SET created_at = now() - %s WHERE llm_call_id = %s",
        (timedelta(days=91), old),
    )

    app_log.purge_expired(conn)

    purged = client.get(f"/api/observability/calls/{old}").json()
    assert purged["user_prompt"] is None and purged["answer"] is None
    assert purged["purged_at"] is not None
    assert Decimal(purged["cost_usd"]) == Decimal("0.00023")
    assert purged["events"] == []
    kept = client.get(f"/api/observability/calls/{recent}").json()
    assert kept["user_prompt"] is not None
    names = [e["name"] for e in client.get("/api/observability/events").json()["events"]]
    assert "journal.purged" in names


def _eval_result(
    directory: Path,
    version: int,
    run_at: str,
    score: float,
    setup: str = "claude-sonnet-5-5.off-medium",
) -> None:
    directory.mkdir(exist_ok=True)
    summary = {
        "suite": "select_cv_content",
        "metric": "cas réussis",
        "prompt_version": version,
        "setup": setup,
        "model": setup.split(".")[0],
        "thinking": "off",
        "effort": "medium",
        "score": score,
        "threshold": None,
        "passed": None,
        "cases": 2,
        "detail": {"cases": "1/2"},
        "spend": {
            "live_calls": 2,
            "cached_calls": 0,
            "input_tokens": 9000,
            "output_tokens": 600,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "cost_usd": "0.024",
            "latency_p50_ms": 4100,
            "latency_p95_ms": 5200,
        },
        "stopped": None,
        "run_at": run_at,
    }
    rows = [
        {"id": "cv-01", "passed": True},
        {"id": "cv-02", "passed": False, "missing": ["skill-django"]},
    ]
    name = f"select_cv_content.v{version}.{setup}.json"
    (directory / name).write_text(json.dumps({"summary": summary, "rows": rows}), encoding="utf-8")


def test_evals_list_every_shipped_task_even_unmeasured(client: TestClient):
    tasks = {task["task"]: task for task in client.get("/api/observability/evals").json()}
    assert set(tasks) == set(TASKS)  # every shipped task, measured or not
    assert tasks["select_cv_content"] == {
        "task": "select_cv_content",
        "shipped_version": SELECT_CV_CONTENT_TASK.prompt_version,
        "current": None,
        "runs": [],
    }


def test_evals_show_the_shipped_version_and_every_run(client: TestClient, settings: Settings):
    results = settings.evals_results_dir
    shipped = SELECT_CV_CONTENT_TASK.prompt_version
    _eval_result(results, shipped, "2026-11-06T10:00:00+00:00", 0.5)
    _eval_result(results, shipped - 1, "2026-11-07T10:00:00+00:00", 0.875)
    (results / "select_cv_content.v9.broken.json").write_text("{", encoding="utf-8")

    tasks = client.get("/api/observability/evals").json()
    [task] = [task for task in tasks if task["task"] == "select_cv_content"]

    assert task["current"]["prompt_version"] == shipped
    assert task["current"]["score"] == 0.5
    assert task["current"]["failing"] == [
        {"id": "cv-02", "passed": False, "missing": ["skill-django"]}
    ]
    assert [run["prompt_version"] for run in task["runs"]] == [shipped - 1, shipped]
    assert Decimal(task["runs"][0]["spend"]["cost_usd"]) == Decimal("0.024")

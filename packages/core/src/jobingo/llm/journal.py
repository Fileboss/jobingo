"""The one way to call the model: render, redact, check the budget, run, journal.

Every call is journalled with its real cost, failed ones included, and the caller gets
the call's id back to store on whatever it derives from the answer.
"""

import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb
from pydantic import BaseModel

from jobingo.db import Conn
from jobingo.domain.personal_data import redact
from jobingo.llm.client import (
    LLMCallError,
    LLMClient,
    LLMResult,
    LLMValidationError,
    Prompt,
    Task,
    Usage,
)
from jobingo.llm.pricing import cost_usd
from jobingo.logs import event

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Budget:
    daily_usd: Decimal
    monthly_usd: Decimal


class LLMBudgetExceeded(Exception):
    """Raised before any call: nothing was sent."""


def render_prompt(
    task: Task[Any, Any], payload: BaseModel, redaction_values: Sequence[str]
) -> Prompt:
    """The prompts as the model will read them. The candidate's known name, e-mail and
    phone become `[CANDIDAT]` in the whole text, whichever field carried them."""
    values = list(redaction_values)
    user = task.prompts.get_template(task.user_template).render(payload=payload)
    system = None
    if task.system_template is not None:
        system = task.prompts.get_template(task.system_template).render(payload=payload)
        system = redact(system, values)
    return Prompt(user=redact(user, values), system=system)


def _local_midnight(day: date) -> datetime:
    """Days and months start at local midnight, compared with UTC timestamps."""
    return datetime.combine(day, time.min).astimezone()


def spent_since(conn: Conn, user_id: int, since: datetime) -> Decimal:
    # Every status counts: a failed call was billed too, and a call that keeps
    # failing must still reach the cap.
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM llm_calls"
        " WHERE user_id = %s AND created_at >= %s",
        (user_id, since),
    ).fetchone()
    assert row is not None
    return row["total"]


def check_budget(conn: Conn, user_id: int, budget: Budget, today: date | None = None) -> None:
    today = today or date.today()
    if spent_since(conn, user_id, _local_midnight(today)) >= budget.daily_usd:
        raise LLMBudgetExceeded("plafond de coût quotidien atteint")
    if spent_since(conn, user_id, _local_midnight(today.replace(day=1))) >= budget.monthly_usd:
        raise LLMBudgetExceeded("plafond de coût mensuel atteint")


def _record(
    conn: Conn,
    user_id: int,
    task: Task[Any, Any],
    input_hash: str,
    *,
    model: str,
    usage: Usage,
    cost: Decimal,
    request: dict[str, Any],
    response: dict[str, Any] | None,
    status: str,
    error: str | None,
) -> int:
    row = conn.execute(
        """
        INSERT INTO llm_calls (
            user_id, task, prompt_version, model, status, error, input_hash, request,
            response, attempts, input_tokens, output_tokens, cache_read_tokens,
            cache_write_tokens, cost_usd, latency_ms
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            user_id,
            task.name,
            task.prompt_version,
            model,
            status,
            error,
            input_hash,
            Jsonb(request),
            None if response is None else Jsonb(response),
            usage.attempts,
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_tokens,
            usage.cache_write_tokens,
            cost,
            usage.latency_ms,
        ),
    ).fetchone()
    assert row is not None
    return row["id"]


def run_task[OutT: BaseModel](
    conn: Conn,
    client: LLMClient,
    budget: Budget,
    user_id: int,
    task: Task[Any, OutT],
    payload: BaseModel,
    *,
    redaction_values: Sequence[str],
) -> tuple[OutT, int]:
    """Returns the validated output and the `llm_calls.id` of the row just written.

    `redaction_values` is required: a caller cannot forget to say what to redact, only
    pass an empty list on purpose.

    Raises `LLMBudgetExceeded` before any call, and `LLMCallError` after journalling the
    failed call with its real cost.
    """
    if not isinstance(payload, task.input_model):
        raise TypeError(f"task {task.name!r} takes {task.input_model.__name__}")
    try:
        check_budget(conn, user_id, budget)
    except LLMBudgetExceeded as exc:
        event(
            log,
            "llm.budget_exceeded",
            logging.WARNING,
            user_id=user_id,
            task=task.name,
            reason=str(exc),
        )
        raise

    prompt = render_prompt(task, payload, redaction_values)
    input_hash = hashlib.sha256(payload.model_dump_json().encode("utf-8")).hexdigest()
    try:
        result: LLMResult[OutT] = client.run(task, prompt)
    except LLMCallError as exc:
        status = "failed" if isinstance(exc, LLMValidationError) else "error"
        cost = cost_usd(exc.model, exc.usage)
        call_id = _record(
            conn,
            user_id,
            task,
            input_hash,
            model=exc.model,
            usage=exc.usage,
            cost=cost,
            request=exc.request,
            response=exc.response,
            status=status,
            error=str(exc),
        )
        event(
            log,
            "llm.call",
            logging.ERROR if status == "error" else logging.WARNING,
            user_id=user_id,
            llm_call_id=call_id,
            task=task.name,
            status=status,
            model=exc.model,
            attempts=exc.usage.attempts,
            cost_usd=str(cost),
            latency_ms=exc.usage.latency_ms,
        )
        raise

    cost = cost_usd(result.model, result.usage)
    call_id = _record(
        conn,
        user_id,
        task,
        input_hash,
        model=result.model,
        usage=result.usage,
        cost=cost,
        request=result.request,
        response=result.response,
        status="ok",
        error=None,
    )
    event(
        log,
        "llm.call",
        user_id=user_id,
        llm_call_id=call_id,
        task=task.name,
        status="ok",
        model=result.model,
        attempts=result.usage.attempts,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        cache_read_tokens=result.usage.cache_read_tokens,
        cost_usd=str(cost),
        latency_ms=result.usage.latency_ms,
    )
    return result.output, call_id

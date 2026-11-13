"""The figures of the observability page, read from the call journal."""

import json
import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from jobingo.config import Settings
from jobingo.db import Conn
from jobingo.domain.observability import (
    BudgetUse,
    CallDetail,
    CallPage,
    CallStatus,
    CallSummary,
    DailyCost,
    EvalRun,
    EvalTask,
    TaskUsage,
    TierModel,
    UsageFigures,
    UsageReport,
)
from jobingo.llm.journal import spent_since
from jobingo.llm.tasks import TASKS
from jobingo.logs import event
from jobingo.services.app_log import list_events

log = logging.getLogger(__name__)

_FIGURES = """
    count(*) AS calls,
    count(*) FILTER (WHERE status = 'ok') AS ok,
    count(*) FILTER (WHERE status = 'failed') AS failed,
    count(*) FILTER (WHERE status = 'error') AS errors,
    count(*) FILTER (WHERE attempts > 1) AS retried,
    COALESCE(sum(input_tokens), 0) AS input_tokens,
    COALESCE(sum(output_tokens), 0) AS output_tokens,
    COALESCE(sum(cache_read_tokens), 0) AS cache_read_tokens,
    COALESCE(sum(cache_write_tokens), 0) AS cache_write_tokens,
    COALESCE(sum(cost_usd), 0) AS cost_usd,
    round(percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms)
        FILTER (WHERE status = 'ok')) AS latency_p50_ms,
    round(percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)
        FILTER (WHERE status = 'ok')) AS latency_p95_ms
"""

_SUMMARY_COLUMNS = """
    id, created_at, task, prompt_version, model, status, error, attempts, input_tokens,
    output_tokens, cache_read_tokens, cache_write_tokens, cost_usd, latency_ms
"""


def _local_midnight(day: date) -> datetime:
    return datetime.combine(day, time.min).astimezone()


def usage_report(conn: Conn, user_id: int, settings: Settings, days: int) -> UsageReport:
    """The last `days` days, today included. Days start at local midnight."""
    today = date.today()
    first_day = today - timedelta(days=days - 1)
    since = _local_midnight(first_day)
    params = {"user_id": user_id, "since": since}
    where = "WHERE user_id = %(user_id)s AND created_at >= %(since)s"

    total = conn.execute(f"SELECT {_FIGURES} FROM llm_calls {where}", params).fetchone()  # nosec B608
    assert total is not None
    tasks = conn.execute(
        f"SELECT task, {_FIGURES} FROM llm_calls {where} GROUP BY task"  # nosec B608
        " ORDER BY sum(cost_usd) DESC, task",
        params,
    ).fetchall()

    per_day: dict[date, DailyCost] = {
        first_day + timedelta(days=n): DailyCost(
            day=first_day + timedelta(days=n), calls=0, cost_usd=Decimal(0)
        )
        for n in range(days)
    }
    for row in conn.execute(f"SELECT created_at, cost_usd FROM llm_calls {where}", params):  # nosec B608
        day = per_day.get(row["created_at"].astimezone().date())
        if day is not None:
            day.calls += 1
            day.cost_usd += row["cost_usd"]

    key = settings.anthropic_api_key
    return UsageReport(
        days=days,
        since=since,
        configured=key is not None and bool(key.get_secret_value()),
        models=[
            TierModel(
                tier="fast",
                model=settings.llm_model_fast,
                thinking=settings.llm_fast_thinking,
                effort=settings.llm_fast_effort,
            ),
            TierModel(
                tier="writing",
                model=settings.llm_model_writing,
                thinking=settings.llm_writing_thinking,
                effort=settings.llm_writing_effort,
            ),
        ],
        total=UsageFigures.model_validate(total),
        tasks=[TaskUsage.model_validate(row) for row in tasks],
        daily=list(per_day.values()),
        budget=BudgetUse(
            today_usd=spent_since(conn, user_id, _local_midnight(today)),
            daily_cap_usd=settings.llm_daily_budget_usd,
            month_usd=spent_since(conn, user_id, _local_midnight(today.replace(day=1))),
            monthly_cap_usd=settings.llm_monthly_budget_usd,
        ),
    )


def list_calls(
    conn: Conn,
    user_id: int,
    *,
    task: str | None = None,
    status: CallStatus | None = None,
    before_id: int | None = None,
    limit: int = 50,
) -> CallPage:
    rows = conn.execute(
        f"""
        SELECT {_SUMMARY_COLUMNS}
        FROM llm_calls
        WHERE user_id = %(user_id)s
          AND (%(task)s::text IS NULL OR task = %(task)s)
          AND (%(status)s::text IS NULL OR status = %(status)s)
          AND (%(before)s::bigint IS NULL OR id < %(before)s)
        ORDER BY id DESC
        LIMIT %(limit)s
        """,  # nosec B608
        {
            "user_id": user_id,
            "task": task,
            "status": status,
            "before": before_id,
            "limit": limit + 1,
        },
    ).fetchall()
    calls = [CallSummary.model_validate(row) for row in rows[:limit]]
    tasks = [
        row["task"]
        for row in conn.execute(
            "SELECT DISTINCT task FROM llm_calls WHERE user_id = %s ORDER BY task", (user_id,)
        )
    ]
    more = len(rows) > limit
    return CallPage(
        calls=calls, next_before_id=calls[-1].id if more and calls else None, tasks=tasks
    )


def _dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        cast(dict[str, Any], item) for item in cast(list[object], value) if isinstance(item, dict)
    ]


def _prompts(request: dict[str, Any]) -> tuple[str | None, str | None, dict[str, Any]]:
    """The system and user prompts of a journalled request, and its other parameters.
    Reads both the Messages API's shape and the fake client's."""
    parameters = {k: v for k, v in request.items() if k not in ("system", "messages", "user")}
    system: object = request.get("system")
    if not isinstance(system, str) and system is not None:
        system = "\n\n".join(str(block.get("text", "")) for block in _dicts(system))
    user = request.get("user")
    messages = _dicts(request.get("messages"))
    if messages:
        content = messages[-1].get("content")
        user = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    return (
        system if isinstance(system, str) else None,
        user if isinstance(user, str) else None,
        parameters,
    )


def _answer(response: dict[str, Any] | None) -> Any:
    """The answer a Messages API response carried, parsed when it is JSON. The fake
    client journals the output itself."""
    if response is None or "content" not in response:
        return response
    for block in _dicts(response["content"]):
        text = block.get("text")
        if block.get("type") == "text" and isinstance(text, str):
            try:
                return json.loads(text)
            except ValueError:
                return text
    return None


def get_call(conn: Conn, user_id: int, call_id: int) -> CallDetail | None:
    row = conn.execute(
        f"SELECT {_SUMMARY_COLUMNS}, request, response, purged_at FROM llm_calls"  # nosec B608
        " WHERE user_id = %s AND id = %s",
        (user_id, call_id),
    ).fetchone()
    if row is None:
        return None
    request = row.pop("request")
    response = row.pop("response")
    system, user, parameters = _prompts(request) if request is not None else (None, None, None)
    return CallDetail(
        **CallSummary.model_validate(row).model_dump(),
        system_prompt=system,
        user_prompt=user,
        parameters=parameters,
        answer=_answer(response),
        response=response,
        purged_at=row["purged_at"],
        events=list_events(conn, user_id, llm_call_id=call_id, limit=200).events,
    )


def _eval_run(path: Path) -> EvalRun | None:
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
        failing = [row for row in _dicts(stored.get("rows")) if not row.get("passed")]
        return EvalRun.model_validate(stored["summary"] | {"failing": failing})
    except (OSError, ValueError, KeyError, TypeError):
        # A file this version cannot read is skipped, and said, rather than hiding
        # every other result.
        event(log, "evals.unreadable", logging.WARNING, file=path.name)
        return None


def eval_report(results_dir: Path) -> list[EvalTask]:
    """Every shipped task, with its recorded eval runs. Reads committed files only:
    nothing here runs an eval or spends anything."""
    report: list[EvalTask] = []
    for name, task in sorted(TASKS.items()):
        paths = sorted(results_dir.glob(f"{name}.v*.json")) if results_dir.is_dir() else []
        runs = [run for path in paths if (run := _eval_run(path)) is not None]
        runs.sort(key=lambda run: run.run_at, reverse=True)
        current = next((r for r in runs if r.prompt_version == task.prompt_version), None)
        report.append(
            EvalTask(task=name, shipped_version=task.prompt_version, current=current, runs=runs)
        )
    return report

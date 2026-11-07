"""What the observability page shows. Every figure here is measured: a count, a sum or a
percentile over journalled calls, never an estimate."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel

type CallStatus = Literal["ok", "failed", "error"]
type EventLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

EVENT_LEVELS: tuple[EventLevel, ...] = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class AppEvent(BaseModel):
    id: int
    created_at: datetime
    level: EventLevel
    name: str
    fields: dict[str, Any]
    llm_call_id: int | None


class EventPage(BaseModel):
    events: list[AppEvent]
    # Pass as `before_id` for the next, older page. None when this one is the last.
    next_before_id: int | None


class UsageFigures(BaseModel):
    calls: int
    ok: int
    failed: int
    errors: int
    # Calls that needed a second API request: both were billed.
    retried: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: Decimal
    # Over successful calls only: a call that fails fast would flatter them. None when
    # there is no successful call to measure.
    latency_p50_ms: int | None
    latency_p95_ms: int | None


class TaskUsage(UsageFigures):
    task: str


class DailyCost(BaseModel):
    day: date
    calls: int
    cost_usd: Decimal


class BudgetUse(BaseModel):
    today_usd: Decimal
    daily_cap_usd: Decimal
    month_usd: Decimal
    monthly_cap_usd: Decimal


class TierModel(BaseModel):
    tier: Literal["fast", "writing"]
    model: str
    thinking: str
    effort: str


class UsageReport(BaseModel):
    days: int
    since: datetime
    configured: bool
    models: list[TierModel]
    total: UsageFigures
    tasks: list[TaskUsage]
    daily: list[DailyCost]
    budget: BudgetUse


class CallSummary(BaseModel):
    id: int
    created_at: datetime
    task: str
    prompt_version: int
    model: str
    status: CallStatus
    error: str | None
    attempts: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: Decimal
    latency_ms: int


class CallPage(BaseModel):
    calls: list[CallSummary]
    next_before_id: int | None
    # Every task with a call, for the filter.
    tasks: list[str]


class CallDetail(CallSummary):
    # The prompts as the model read them, after redaction. None once purged.
    system_prompt: str | None
    user_prompt: str | None
    # The request's other parameters: model, max_tokens, thinking, effort, schema.
    parameters: dict[str, Any] | None
    # The validated answer when it can be read back, else the raw response.
    answer: Any
    response: dict[str, Any] | None
    purged_at: datetime | None
    # What the app logged about this call: the trail from the call to what it caused.
    events: list[AppEvent]

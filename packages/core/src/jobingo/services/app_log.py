"""The application log, kept in `app_events`, and the retention of prompts and answers.

Only structured events (`jobingo.logs.event`) are stored; plain log lines stay on the
console. String fields are redacted again before they are stored: an event should
never carry the candidate's identity, and this is the second line of defence.
"""

import logging
from collections.abc import Mapping
from datetime import timedelta
from typing import Any, cast

from psycopg.types.json import Jsonb

from jobingo.db import Conn, Pool
from jobingo.domain.observability import EVENT_LEVELS, AppEvent, EventLevel, EventPage
from jobingo.domain.personal_data import redact
from jobingo.logs import event
from jobingo.services.identity import redaction_values

log = logging.getLogger(__name__)

RETENTION = timedelta(days=90)


def _json_safe(value: object, values: list[str]) -> Any:
    if isinstance(value, str):
        return redact(value, values) if values else value
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, Mapping):
        items = cast(Mapping[object, object], value).items()
        return {str(k): _json_safe(v, values) for k, v in items}
    if isinstance(value, list | tuple):
        return [_json_safe(v, values) for v in cast(list[object], value)]
    return _json_safe(str(value), values)


class DatabaseEventHandler(logging.Handler):
    """Writes each structured event to `app_events`, on its own connection, so that an
    event outlives a request that fails afterwards."""

    def __init__(self, pool: Pool) -> None:
        super().__init__(logging.INFO)
        self._pool = pool

    def emit(self, record: logging.LogRecord) -> None:
        name = getattr(record, "event", None)
        if not isinstance(name, str):
            return
        try:
            fields: dict[str, Any] = dict(getattr(record, "fields", {}))
            user_id = fields.pop("user_id", None)
            llm_call_id = fields.get("llm_call_id")
            with self._pool.connection() as conn:
                values = redaction_values(conn, user_id) if isinstance(user_id, int) else []
                conn.execute(
                    """
                    INSERT INTO app_events (user_id, level, name, logger, fields, llm_call_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        user_id if isinstance(user_id, int) else None,
                        record.levelname if record.levelname in EVENT_LEVELS else "INFO",
                        name,
                        record.name,
                        Jsonb(_json_safe(fields, values)),
                        llm_call_id if isinstance(llm_call_id, int) else None,
                    ),
                )
        except Exception:
            self.handleError(record)


def install(pool: Pool) -> DatabaseEventHandler:
    handler = DatabaseEventHandler(pool)
    logger = logging.getLogger("jobingo")
    if logger.level == logging.NOTSET or logger.level > logging.INFO:
        logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return handler


def uninstall(handler: DatabaseEventHandler) -> None:
    logging.getLogger("jobingo").removeHandler(handler)


def list_events(
    conn: Conn,
    user_id: int,
    *,
    min_level: EventLevel = "DEBUG",
    text: str | None = None,
    llm_call_id: int | None = None,
    before_id: int | None = None,
    limit: int = 100,
) -> EventPage:
    """Newest first. Events about no account, such as a purge, are shown too: they hold
    no one's data."""
    levels = list(EVENT_LEVELS[EVENT_LEVELS.index(min_level) :])
    pattern = None
    if text:
        escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
    rows = conn.execute(
        """
        SELECT id, created_at, level, name, fields, llm_call_id
        FROM app_events
        WHERE (user_id = %(user_id)s OR user_id IS NULL)
          AND level = ANY(%(levels)s)
          AND (%(pattern)s::text IS NULL
               OR name ILIKE %(pattern)s OR fields::text ILIKE %(pattern)s)
          AND (%(call)s::bigint IS NULL OR llm_call_id = %(call)s)
          AND (%(before)s::bigint IS NULL OR id < %(before)s)
        ORDER BY id DESC
        LIMIT %(limit)s
        """,
        {
            "user_id": user_id,
            "levels": levels,
            "pattern": pattern,
            "call": llm_call_id,
            "before": before_id,
            "limit": limit + 1,
        },
    ).fetchall()
    events = [AppEvent.model_validate(row) for row in rows[:limit]]
    more = len(rows) > limit
    return EventPage(events=events, next_before_id=events[-1].id if more and events else None)


def purge_expired(conn: Conn) -> None:
    """Drop prompts and answers older than the retention, keeping counts and costs, and
    delete events as old."""
    with conn.transaction():
        calls = conn.execute(
            """
            UPDATE llm_calls SET request = NULL, response = NULL, purged_at = now()
            WHERE purged_at IS NULL AND created_at < now() - %s
            """,
            (RETENTION,),
        ).rowcount
        events = conn.execute(
            "DELETE FROM app_events WHERE created_at < now() - %s", (RETENTION,)
        ).rowcount
    if calls or events:
        event(log, "journal.purged", calls=calls, events=events, retention_days=RETENTION.days)

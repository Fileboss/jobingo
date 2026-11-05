from collections.abc import Sequence
from importlib import resources

import psycopg
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool

type Conn = psycopg.Connection[DictRow]
type Pool = ConnectionPool[Conn]

# Connections autocommit: code that writes more than one statement opens
# `conn.transaction()` itself, so a write is committed before the response leaves.
_MIGRATION_LOCK = 7_203_114


def connect(database_url: str) -> Conn:
    return psycopg.Connection[DictRow].connect(database_url, autocommit=True, row_factory=dict_row)


def create_pool(database_url: str) -> Pool:
    return ConnectionPool(
        database_url,
        connection_class=psycopg.Connection[DictRow],
        kwargs={"autocommit": True, "row_factory": dict_row},
        min_size=1,
        max_size=10,
        open=False,
    )


def _migration_files() -> list[tuple[str, bytes]]:
    directory = resources.files("jobingo") / "migrations"
    files = sorted(
        (path for path in directory.iterdir() if path.name.endswith(".sql")),
        key=lambda path: path.name,
    )
    return [(path.name, path.read_bytes()) for path in files]


def migrate(conn: Conn, migrations: Sequence[tuple[str, bytes]] | None = None) -> list[str]:
    """Apply pending numbered SQL migrations, returning the names applied.

    One transaction covers the whole run: a failure leaves the schema as it was,
    and the lock makes a second process wait instead of applying them twice.
    """
    applied: list[str] = []
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_MIGRATION_LOCK,))
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                name TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        done = {row["name"] for row in conn.execute("SELECT name FROM schema_migrations")}
        for name, sql in _migration_files() if migrations is None else migrations:
            if name in done:
                continue
            conn.execute(sql)
            conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (name,))
            applied.append(name)
    return applied

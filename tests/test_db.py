from pathlib import Path

import psycopg
import pytest

import jobingo
from jobingo.db import Conn, migrate


def _table_exists(conn: Conn, name: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS found", (name,)).fetchone()
    assert row is not None
    return row["found"] is not None


def test_the_shipped_migrations_are_recorded_and_not_applied_twice(conn: Conn):
    names = [row["name"] for row in conn.execute("SELECT name FROM schema_migrations")]
    assert "0001_users.sql" in names
    assert migrate(conn) == []


def test_migration_numbers_are_unique():
    """Two branches can pick the same number: the second to merge has to renumber."""
    numbers = [
        path.name.split("_")[0]
        for path in (Path(jobingo.__file__).parent / "migrations").glob("*.sql")
    ]
    assert numbers
    assert len(numbers) == len(set(numbers))


def test_a_new_migration_is_applied_once(conn: Conn):
    migration = ("9000_probe.sql", b"CREATE TABLE migration_probe (id INT);")
    try:
        assert migrate(conn, [migration]) == ["9000_probe.sql"]
        assert migrate(conn, [migration]) == []
        assert _table_exists(conn, "migration_probe")
    finally:
        conn.execute("DROP TABLE IF EXISTS migration_probe")
        conn.execute("DELETE FROM schema_migrations WHERE name = '9000_probe.sql'")


def test_a_failing_run_leaves_the_schema_untouched(conn: Conn):
    migrations = [
        ("9001_good.sql", b"CREATE TABLE migration_good (id INT);"),
        ("9002_bad.sql", b"CREATE TABLE migration_bad (id INT); SELECT not_a_column;"),
    ]
    with pytest.raises(psycopg.errors.UndefinedColumn):
        migrate(conn, migrations)

    assert not _table_exists(conn, "migration_good")
    assert not _table_exists(conn, "migration_bad")
    row = conn.execute(
        "SELECT count(*) AS n FROM schema_migrations WHERE name LIKE '900%'"
    ).fetchone()
    assert row is not None and row["n"] == 0

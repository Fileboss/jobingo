import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.conninfo import make_conninfo
from psycopg.sql import SQL, Identifier
from pydantic_settings import SettingsConfigDict

from jobingo.config import Settings
from jobingo.db import Conn, connect, migrate
from jobingo_api.main import create_app

# A server, not a database: each test run creates and drops its own database.
SERVER_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://jobingo:jobingo@127.0.0.1:5433/postgres"
)


class _TestSettings(Settings):
    """Never reads the developer's `.env`."""

    model_config = SettingsConfigDict(env_file=None)


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    name = f"jobingo_test_{uuid4().hex}"
    try:
        admin = psycopg.connect(SERVER_URL, autocommit=True)
    except psycopg.OperationalError as error:
        pytest.exit(f"Postgres is unreachable, run `make db-up`: {error}", returncode=1)
    with admin:
        admin.execute(SQL("CREATE DATABASE {}").format(Identifier(name)))
        try:
            url = make_conninfo(SERVER_URL, dbname=name)
            with connect(url) as conn:
                migrate(conn)
            yield url
        finally:
            admin.execute(SQL("DROP DATABASE {} WITH (FORCE)").format(Identifier(name)))


@pytest.fixture
def conn(database_url: str) -> Iterator[Conn]:
    with connect(database_url) as connection:
        yield connection
        connection.execute("TRUNCATE users RESTART IDENTITY CASCADE")


@pytest.fixture
def settings(database_url: str, tmp_path: Path) -> Settings:
    """No client build, unless a test writes one."""
    return _TestSettings(
        database_url=database_url,
        account_username="test-account",
        api_port=8000,  # not a worktree's, which `make test` exports
        web_port=5173,
        web_build_dir=tmp_path / "no-client-build",
        evals_results_dir=tmp_path / "eval-results",
    )


@pytest.fixture
def client(settings: Settings, conn: Conn) -> Iterator[TestClient]:
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as test_client:
        yield test_client

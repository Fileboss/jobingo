"""Development data must survive: the user should never have to recreate their account
or re-enter their CV because the server restarted."""

from fastapi.testclient import TestClient

from jobingo.config import Settings
from jobingo.db import Conn, migrate
from jobingo.services.accounts import ensure_account, get_account
from jobingo_api.main import create_app


def test_a_restart_keeps_existing_accounts(settings: Settings, conn: Conn):
    other = ensure_account(conn, "someone-else")
    configured = ensure_account(conn, settings.account_username)

    for _ in range(2):
        with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
            assert client.get("/api/me").json()["id"] == configured.id

    assert get_account(conn, "someone-else") == other


def test_running_migrations_again_changes_nothing(conn: Conn):
    account = ensure_account(conn, "alex")

    assert migrate(conn) == []
    assert get_account(conn, "alex") == account

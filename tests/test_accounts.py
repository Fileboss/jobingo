from jobingo.db import Conn
from jobingo.services.accounts import ensure_account, get_account


def test_ensure_account_creates_the_account_once(conn: Conn):
    first = ensure_account(conn, "alex")
    second = ensure_account(conn, "alex")

    assert first == second
    assert first.username == "alex"


def test_accounts_are_distinct(conn: Conn):
    assert ensure_account(conn, "alex").id != ensure_account(conn, "sam").id


def test_an_unknown_account_is_none(conn: Conn):
    assert get_account(conn, "nobody") is None

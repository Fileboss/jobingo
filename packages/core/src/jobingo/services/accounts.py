from jobingo.db import Conn
from jobingo.domain.users import User


def get_account(conn: Conn, username: str) -> User | None:
    row = conn.execute(
        "SELECT id, username FROM users WHERE username = %s",
        (username,),
    ).fetchone()
    return None if row is None else User.model_validate(row)


def ensure_account(conn: Conn, username: str) -> User:
    conn.execute(
        "INSERT INTO users (username) VALUES (%s) ON CONFLICT (username) DO NOTHING",
        (username,),
    )
    account = get_account(conn, username)
    assert account is not None
    return account

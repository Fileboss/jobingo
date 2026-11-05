"""Create or drop a worktree's development database.

Usage: `dev_db.py create|drop <name>`. A new database starts empty: the API applies the
migrations at startup. The main database, which holds the user's real data, is refused.
"""

import os
import sys

import psycopg
from psycopg.sql import SQL, Identifier

SERVER_URL = os.environ.get(
    "POSTGRES_SERVER_URL", "postgresql://jobingo:jobingo@127.0.0.1:5433/postgres"
)
MAIN_DATABASE = "jobingo"


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in ("create", "drop"):
        print("usage: dev_db.py create|drop <name>", file=sys.stderr)
        return 2
    action, name = sys.argv[1:]
    if name == MAIN_DATABASE:
        print("refused: this is the main database", file=sys.stderr)
        return 1

    try:
        admin = psycopg.connect(SERVER_URL, autocommit=True)
    except psycopg.OperationalError as error:
        print(f"Postgres is unreachable, run `make db-up`: {error}", file=sys.stderr)
        return 1
    with admin:
        if action == "drop":
            admin.execute(SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(Identifier(name)))
            return 0
        try:
            admin.execute(SQL("CREATE DATABASE {}").format(Identifier(name)))
        except psycopg.errors.DuplicateDatabase:
            print(f"database {name} already exists, keeping it")
    return 0


if __name__ == "__main__":
    sys.exit(main())

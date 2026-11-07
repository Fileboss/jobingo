from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from jobingo.config import Settings
from jobingo.db import Conn, Pool
from jobingo.domain.users import User
from jobingo.llm.client import LLMClient
from jobingo.llm.factory import budget
from jobingo.llm.journal import Budget
from jobingo.services.accounts import get_account


def get_pool(request: Request) -> Pool:
    return request.app.state.pool


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(pool: Annotated[Pool, Depends(get_pool)]) -> Iterator[Conn]:
    with pool.connection() as conn:
        yield conn


DbConn = Annotated[Conn, Depends(get_db)]


def get_current_user(conn: DbConn, settings: Annotated[Settings, Depends(get_settings)]) -> User:
    """Who is calling. The only place to change when real authentication arrives."""
    user = get_account(conn, settings.account_username)
    if user is None:
        raise RuntimeError("the account is created at startup")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_llm_client(request: Request) -> LLMClient | None:
    """None without an API key. Built once at startup; tests put a fake in its place."""
    return request.app.state.llm_client


LlmClient = Annotated[LLMClient | None, Depends(get_llm_client)]


def get_budget(settings: Annotated[Settings, Depends(get_settings)]) -> Budget:
    return budget(settings)


LlmBudget = Annotated[Budget, Depends(get_budget)]

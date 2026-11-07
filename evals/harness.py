"""The eval harness: its own key, a cache of answers, a spending cap, and a throwaway
database that the real services run against.

Nothing here touches the user's database or budget: each suite runs in a new database
seeded from `evals/fixtures/`, dropped at the end.
"""

import hashlib
import json
import os
import statistics
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import anthropic
import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.sql import SQL, Identifier
from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from jobingo.config import Settings
from jobingo.db import Conn, connect, migrate
from jobingo.domain.style import StyleGuide, parse_style
from jobingo.llm.anthropic_client import AnthropicLLMClient, TierSettings
from jobingo.llm.client import (
    LLMClient,
    LLMResult,
    LLMUnavailable,
    LLMValidationError,
    Prompt,
    Task,
    Tier,
    Usage,
)
from jobingo.llm.journal import Budget
from jobingo.llm.pricing import cost_usd
from jobingo.services.accounts import ensure_account

EVALS_DIR = Path(__file__).resolve().parent
CACHE_DIR = EVALS_DIR / ".cache"
KEY_FILE = EVALS_DIR / ".env"
FIXTURES = EVALS_DIR / "fixtures"
SERVER_URL = os.environ.get(
    "POSTGRES_SERVER_URL", "postgresql://jobingo:jobingo@127.0.0.1:5433/postgres"
)
# The eval's own cap is `CachingClient.max_usd`: the app's caps must never stop a run.
NO_BUDGET = Budget(Decimal(10**6), Decimal(10**6))


class EvalBudgetExceededError(Exception):
    pass


class EvalConfig(BaseSettings):
    """Read from `evals/.env` only, never from the app's `.env` or the shell: eval spend
    stays on its own key, which can carry its own spend limit and be revoked alone.
    Models and settings default to the app's, so a run measures what the app ships."""

    model_config = SettingsConfigDict(env_file=KEY_FILE, extra="ignore")

    anthropic_api_key: SecretStr | None = None
    llm_model_fast: str = Settings.model_fields["llm_model_fast"].default
    llm_fast_thinking: Literal["off", "adaptive"] = Settings.model_fields[
        "llm_fast_thinking"
    ].default
    llm_fast_effort: Literal["low", "medium", "high", "xhigh", "max"] = Settings.model_fields[
        "llm_fast_effort"
    ].default
    llm_model_writing: str = Settings.model_fields["llm_model_writing"].default
    llm_writing_thinking: Literal["off", "adaptive"] = Settings.model_fields[
        "llm_writing_thinking"
    ].default
    llm_writing_effort: Literal["low", "medium", "high", "xhigh", "max"] = Settings.model_fields[
        "llm_writing_effort"
    ].default

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, dotenv_settings)

    def tiers(self) -> dict[Tier, TierSettings]:
        return {
            "fast": TierSettings(self.llm_model_fast, self.llm_fast_thinking, self.llm_fast_effort),
            "writing": TierSettings(
                self.llm_model_writing, self.llm_writing_thinking, self.llm_writing_effort
            ),
        }

    def setup(self, tier: Tier) -> str:
        """What besides the prompt decides a result: part of the results' file name, so
        trying another model never overwrites a baseline."""
        settings = self.tiers()[tier]
        return f"{settings.model}.{settings.thinking}-{settings.effort}"

    def api_key(self) -> str:
        key = self.anthropic_api_key.get_secret_value() if self.anthropic_api_key else ""
        if not key:
            raise SystemExit(
                f"No eval key. Put ANTHROPIC_API_KEY=... in {KEY_FILE}, then chmod 600.\n"
                "The app's key is never used by `make eval`."
            )
        return key


@dataclass
class Spend:
    live_calls: int = 0
    cached_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: Decimal = Decimal(0)
    latencies_ms: list[int] = field(default_factory=list[int])

    def add(self, model: str, usage: Usage) -> None:
        self.live_calls += 1
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.cache_read_tokens += usage.cache_read_tokens
        self.cache_write_tokens += usage.cache_write_tokens
        self.cost_usd += cost_usd(model, usage)
        self.latencies_ms.append(usage.latency_ms)

    def summary(self) -> dict[str, Any]:
        latencies = sorted(self.latencies_ms)
        return {
            "live_calls": self.live_calls,
            "cached_calls": self.cached_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cost_usd": str(self.cost_usd),
            "latency_p50_ms": int(statistics.median(latencies)) if latencies else None,
            "latency_p95_ms": latencies[int(0.95 * (len(latencies) - 1))] if latencies else None,
        }


class _Stored(BaseModel):
    model: str
    output: dict[str, Any] | None = None
    error: str | None = None


class CachingClient:
    """An `LLMClient` that answers from `evals/.cache/` when it can and calls the API
    otherwise. The key is the exact request the client would send: rendered prompts,
    model, schema, thinking and effort. An unchanged re-run costs nothing, and any
    change to those is a miss.

    Before each live call it checks the run's spend against `max_usd`. Invalid answers
    are cached too, so a failing case fails again without paying again; an outage is
    not, since it says nothing about the prompt.
    """

    def __init__(
        self,
        inner: AnthropicLLMClient,
        max_usd: Decimal,
        cache_dir: Path = CACHE_DIR,
        live: LLMClient | None = None,
    ) -> None:
        self._inner = inner
        # What runs a miss: the inner client, or a stand-in in the harness's own tests.
        self._live: LLMClient = live or inner
        self.max_usd = max_usd
        self.cache_dir = cache_dir
        self.spend = Spend()

    def _path(self, task: Task[Any, Any], prompt: Prompt) -> Path:
        request = json.dumps(self._inner.params(task, prompt), sort_keys=True, ensure_ascii=False)
        key = hashlib.sha256(request.encode("utf-8")).hexdigest()
        return self.cache_dir / task.name / f"{key}.json"

    def run[OutT: BaseModel](self, task: Task[Any, OutT], prompt: Prompt) -> LLMResult[OutT]:
        path = self._path(task, prompt)
        request = self._inner.params(task, prompt)
        if path.exists():
            stored = _Stored.model_validate_json(path.read_text(encoding="utf-8"))
            self.spend.cached_calls += 1
            if stored.error is not None:
                raise LLMValidationError(
                    stored.error, model=stored.model, usage=Usage(), request=request
                )
            assert stored.output is not None
            return LLMResult(
                output=task.output_model.model_validate(stored.output),
                model=stored.model,
                usage=Usage(),
                request=request,
                response=stored.output,
            )

        if self.spend.cost_usd >= self.max_usd:
            raise EvalBudgetExceededError(
                f"eval spend reached {self.spend.cost_usd} $ (cap {self.max_usd} $). Cached "
                "answers are kept: run again with a higher --max-usd to go on."
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = self._live.run(task, prompt)
        except LLMValidationError as exc:
            self.spend.add(exc.model, exc.usage)
            path.write_text(_Stored(model=exc.model, error=str(exc)).model_dump_json())
            raise
        except LLMUnavailable as exc:
            self.spend.add(exc.model, exc.usage)
            raise
        self.spend.add(result.model, result.usage)
        stored = _Stored(model=result.model, output=result.output.model_dump(mode="json"))
        path.write_text(stored.model_dump_json(), encoding="utf-8")
        return result


def anthropic_client(config: EvalConfig) -> AnthropicLLMClient:
    return AnthropicLLMClient(anthropic.Anthropic(api_key=config.api_key()), config.tiers())


class Workspace:
    """A new database with the fictional profile: what the app has on a user's machine,
    minus the user. Dropped on `close`."""

    def __init__(self, server_url: str = SERVER_URL) -> None:
        self._server_url = server_url
        self._name = f"jobingo_eval_{uuid4().hex}"
        with psycopg.connect(server_url, autocommit=True) as admin:
            admin.execute(SQL("CREATE DATABASE {}").format(Identifier(self._name)))
        self.conn: Conn = connect(make_conninfo(server_url, dbname=self._name))
        migrate(self.conn)
        self.user_id = ensure_account(self.conn, "alex-moreau").id
        cv = (FIXTURES / "cv.fr.md").read_text(encoding="utf-8")
        # A throwaway database, seeded as a user's save would leave it.
        self.conn.execute(
            "INSERT INTO cv_versions (user_id, lang, version, content) VALUES (%s, 'fr', 1, %s)",
            (self.user_id, cv),
        )
        self.style: StyleGuide = parse_style((FIXTURES / "style.md").read_text(encoding="utf-8"))

    def close(self) -> None:
        self.conn.close()
        with psycopg.connect(self._server_url, autocommit=True) as admin:
            admin.execute(
                SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(Identifier(self._name))
            )

    def __enter__(self) -> "Workspace":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

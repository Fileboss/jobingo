from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://jobingo:jobingo@127.0.0.1:5433/jobingo"
    # The one account, created at startup until accounts can be created in the app.
    account_username: str = "owner"

    allowed_hosts: list[str] = ["127.0.0.1", "localhost"]
    # Each worktree has its own (scripts/worktree.sh). WEB_PORT is the Vite dev server's.
    api_port: int = 8000
    web_port: int = 5173
    web_build_dir: Path = Path("apps/web/build")
    # Committed eval results, read by the observability page. Runs are `make eval`.
    evals_results_dir: Path = Path("evals/results")

    # The mailbox the app reads and sends from. The defaults are the local servers of
    # docker-compose.yml (`make mail-up`); the Gmail values in .env replace them. The
    # passwords are server-side only, never shown or sent to the client.
    mail_imap_host: str = "127.0.0.1"
    mail_imap_port: int = 3143
    mail_imap_ssl: bool = False
    mail_imap_user: str = "alex@jobingo.test"
    mail_imap_password: SecretStr = SecretStr("jobingo")
    mail_inbox_folder: str = "INBOX"
    # Where job alerts land, when a filter moves them out of the inbox.
    mail_alert_folder: str = "INBOX"
    mail_smtp_host: str = "127.0.0.1"
    mail_smtp_port: int = 1025
    mail_smtp_ssl: bool = False
    mail_smtp_user: str = ""
    mail_smtp_password: SecretStr | None = None
    mail_from: str = "alex@jobingo.test"
    # Nothing is sent unless this is turned off, whatever the server.
    smtp_dry_run: bool = True

    # Without a key the app runs, and the AI features say they are not configured.
    anthropic_api_key: SecretStr | None = None
    # Starting hypotheses, adopted only once an eval measures them (docs/porting.md).
    # Thinking "off" sends `disabled`, or `between_tools` on Sonnet 5.5: both accept
    # effort low, medium or high only.
    llm_model_fast: str = "claude-haiku-5-5"
    llm_fast_thinking: Literal["off", "adaptive"] = "off"
    llm_fast_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    llm_model_writing: str = "claude-sonnet-5-5"
    llm_writing_thinking: Literal["off", "adaptive"] = "off"
    llm_writing_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    # Caps on what the model may cost, failed calls included. USD, like the prices.
    llm_daily_budget_usd: Decimal = Decimal(2)
    llm_monthly_budget_usd: Decimal = Decimal(30)

    @property
    def allowed_origins(self) -> list[str]:
        return [
            f"http://{host}:{port}"
            for host in self.allowed_hosts
            for port in (self.api_port, self.web_port)
        ]

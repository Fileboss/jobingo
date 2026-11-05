from pathlib import Path

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

    @property
    def allowed_origins(self) -> list[str]:
        return [
            f"http://{host}:{port}"
            for host in self.allowed_hosts
            for port in (self.api_port, self.web_port)
        ]

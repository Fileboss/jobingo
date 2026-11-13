"""CI starts the servers the tests reach, as docker-compose.yml sets them up locally."""

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).parent.parent


def _load(path: str) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    return loaded


def test_the_backend_job_runs_every_default_compose_service():
    """Mailpit was missing from CI: the approval queue's tests failed there only."""
    compose: dict[str, Any] = _load("docker-compose.yml")["services"]
    local = {name: s["image"] for name, s in compose.items() if "profiles" not in s}
    ci: dict[str, Any] = _load(".github/workflows/ci.yml")["jobs"]["backend"]["services"]
    assert {name: s["image"] for name, s in ci.items()} == local

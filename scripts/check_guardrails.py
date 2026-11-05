"""Verify Claude Code's guardrails: the deny rules and hooks in `.claude/settings.json`
exist, and each hook refuses what it must and lets the legitimate case through.

The hooks are fed synthetic tool payloads, the same JSON Claude Code sends them.
`guard-edits.sh` runs against a throwaway git repository so its answers don't depend
on what happens to be modified in the real working tree.

Usage: `make check-guardrails`. Exit status 1 lists every check that failed.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / ".claude" / "settings.json"
HOOKS = ROOT / ".claude" / "hooks"

REQUIRED_DENY = [
    "Read(./.env)",
    "Read(./evals/.env)",
    "Read(./data/**)",
    "Read(../my-job-processor/.env)",
    "Read(../my-job-processor/evals/.env)",
    "Read(../my-job-processor/data/**)",
    "Read(../../my-job-processor/.env)",
    "Read(../../my-job-processor/evals/.env)",
    "Read(../../my-job-processor/data/**)",
    "Read(../../jobingo/.env)",
    "Read(../../jobingo/data/**)",
    "Edit(./.env)",
    "Edit(./evals/.env)",
    "Edit(./data/**)",
    "Bash(git push *)",
    "Bash(git reset --hard *)",
    "Bash(curl *)",
    "Bash(wget *)",
    "Bash(ssh *)",
    "Bash(psql *)",
    "Bash(docker exec *)",
    "Bash(docker compose exec *)",
]
REQUIRED_DENY_READ = [
    "./.env",
    "./evals/.env",
    "./data",
    "../my-job-processor/.env",
    "../my-job-processor/evals/.env",
    "../my-job-processor/data",
    "../../my-job-processor/.env",
    "../../my-job-processor/evals/.env",
    "../../my-job-processor/data",
    "../../jobingo/.env",
    "../../jobingo/data",
]
MIGRATIONS = "packages/core/src/jobingo/migrations"
EXECUTOR = "packages/core/src/jobingo/hitl/executor.py"
CONTRACT = "apps/web/openapi.json"
SMTP_IMPORT = "from jobingo.connectors import smtp\n"


def _run_hook(
    script: str, payload: dict[str, Any], project_dir: Path, role: str | None = None
) -> int:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project_dir)}
    env.pop("JOBINGO_ROLE", None)
    if role:
        env["JOBINGO_ROLE"] = role
    result = subprocess.run(
        ["sh", str(HOOKS / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return result.returncode


def check_settings() -> list[str]:
    failures: list[str] = []
    settings: dict[str, Any] = json.loads(SETTINGS.read_text(encoding="utf-8"))
    deny = settings.get("permissions", {}).get("deny", [])
    failures += [f"missing deny rule {rule}" for rule in REQUIRED_DENY if rule not in deny]

    sandbox = settings.get("sandbox", {})
    if not sandbox.get("enabled"):
        failures.append("sandbox is not enabled")
    deny_read = sandbox.get("filesystem", {}).get("denyRead", [])
    failures += [f"missing sandbox denyRead {p}" for p in REQUIRED_DENY_READ if p not in deny_read]

    hooks = settings.get("hooks", {})
    wired = json.dumps(hooks)
    for script in (
        "block-dotenv.sh",
        "guard-edits.sh",
        "stop-checks.sh",
        "remind-records.sh",
        "remind-decision.sh",
    ):
        if script not in wired:
            failures.append(f"hook {script} is not wired in settings.json")
    if "Stop" not in hooks:
        failures.append("no Stop hook")
    return failures


def _bash(command: str) -> dict[str, Any]:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _edit(project: Path, rel: str, text: str = "x = 1\n") -> dict[str, Any]:
    return {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(project / rel), "new_string": text},
    }


def _scratch_repo(base: Path) -> Path:
    """A git repo with one committed (applied) migration and an executor."""
    repo = base / "repo"
    (repo / MIGRATIONS).mkdir(parents=True)
    (repo / EXECUTOR).parent.mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / MIGRATIONS / "0001_init.sql").write_text("-- applied\n")
    (repo / EXECUTOR).write_text("\n")
    (repo / "tests/test_hitl.py").write_text("\n")
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-qm", "init"], check=True)
    return repo


def check_hooks() -> list[str]:
    failures: list[str] = []
    # (description, script, payload, expected exit code)
    cases: list[tuple[str, str, dict[str, Any], int]] = [
        ("cat .env is refused", "block-dotenv.sh", _bash("cat .env"), 2),
        ("reading evals/.env is refused", "block-dotenv.sh", _bash("cat evals/.env"), 2),
        ("sourcing .env is refused", "block-dotenv.sh", _bash("source .env && env"), 2),
        (".env.example stays readable", "block-dotenv.sh", _bash("cat .env.example"), 0),
        ("ordinary commands pass", "block-dotenv.sh", _bash("uv run pytest -q"), 0),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        repo = _scratch_repo(Path(tmp))
        edits: list[tuple[str, dict[str, Any], int]] = [
            (
                "editing an applied migration is refused",
                _edit(repo, f"{MIGRATIONS}/0001_init.sql"),
                2,
            ),
            ("a new migration is allowed", _edit(repo, f"{MIGRATIONS}/0099_new.sql"), 0),
            (
                "importing smtp from a service is refused",
                _edit(repo, "packages/core/src/jobingo/services/offers.py", SMTP_IMPORT),
                2,
            ),
            (
                "importing smtp from the API is refused",
                _edit(repo, "apps/api/src/jobingo_api/routes/mail.py", SMTP_IMPORT),
                2,
            ),
            (
                "prose naming the smtp connector is allowed",
                _edit(repo, "docs/notes.md", SMTP_IMPORT),
                0,
            ),
            (
                "editing the executor without a test change is refused",
                _edit(repo, EXECUTOR, SMTP_IMPORT),
                2,
            ),
        ]
        edits.append(
            ("hand-editing the generated contract is refused", _edit(repo, CONTRACT), 2),
        )
        cases += [(name, "guard-edits.sh", payload, code) for name, payload, code in edits]
        for description, script, payload, expected in cases:
            code = _run_hook(script, payload, repo)
            if code != expected:
                failures.append(f"{description}: exit {code}, expected {expected}")

        # (role, file, expected exit code)
        ownership = [
            ("front", "apps/web/src/routes/+page.svelte", 0),
            ("front", "apps/api/src/jobingo_api/main.py", 2),
            ("front", "packages/core/src/jobingo/db.py", 2),
            ("front", "tests/test_db.py", 2),
            ("front", "pyproject.toml", 2),
            ("front", "CLAUDE.md", 0),
            ("back", "apps/api/src/jobingo_api/main.py", 0),
            ("back", "packages/core/src/jobingo/db.py", 0),
            ("back", "apps/web/src/routes/+page.svelte", 2),
            ("back", "apps/web/package.json", 2),
            ("back", "CLAUDE.md", 0),
            ("full", "apps/web/src/routes/+page.svelte", 0),
            ("full", "apps/api/src/jobingo_api/main.py", 0),
        ]
        for role, rel, expected in ownership:
            code = _run_hook("guard-edits.sh", _edit(repo, rel), repo, role)
            if code != expected:
                failures.append(f"{role} editing {rel}: exit {code}, expected {expected}")

        # Once its test has changed, the executor may change too.
        (repo / "tests/test_hitl.py").write_text("# new case\n")
        code = _run_hook("guard-edits.sh", _edit(repo, EXECUTOR, SMTP_IMPORT), repo)
        if code != 0:
            failures.append(f"executor edit after a test change: exit {code}, expected 0")
    return failures


def main() -> int:
    failures = check_settings() + check_hooks()
    for failure in failures:
        print(f"FAIL {failure}")
    if not failures:
        print("guardrails OK")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

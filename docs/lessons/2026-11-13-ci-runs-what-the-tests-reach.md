---
date: 2026-11-13
status: active
applies_when: adding a server the tests reach, a static check to CI, or code that a CI check flags; or before reporting work as done when CI is red
---

# CI runs every server the tests reach, and a red CI is fixed, not left

## What happened

The user found CI red. Two jobs had failed for several pushes. Backend: the approval queue's tests read Mailpit, which `docker-compose.yml` starts locally but the CI job never did, so 11 tests errored in CI only. Security: bandit flagged SQL f-strings that insert only module constants, and the prompts' Jinja environment without autoescape. Every local check passed, so no session saw it.

## What to do instead

- When tests start reaching a new server, add it to the CI backend job in the same commit, with the same image.
- After a push, check the CI run (`gh run list`) and report it; a local `make check` does not run bandit, pip-audit or gitleaks.
- A bandit finding that is a false positive gets a `# nosec <id>` on the flagged line, with the reason stated once nearby, never a blanket skip.

## Prevention

`test_the_backend_job_runs_every_default_compose_service` (`tests/test_ci.py`): CI's backend services and images equal the compose services outside a profile.

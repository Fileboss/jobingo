# In a worktree, this file sets its ports and database (scripts/worktree.sh).
-include .jobingo-worktree

API_PORT ?= 8000
export

.PHONY: db-up db-down mail-up api web api-types test lint typecheck check check-guardrails \
	e2e eval agent agent-front agent-back pair worktree worktree-rm

db-up:
	docker compose up -d --wait postgres

# Local mail servers for development and tests: Mailpit (SMTP, http://127.0.0.1:8025)
# and GreenMail (IMAP, a fictional mailbox, empty at each start).
mail-up:
	docker compose up -d mailpit greenmail

db-down:
	docker compose down

api:
	uv run uvicorn --factory jobingo_api.main:create_app --host 127.0.0.1 --port $(API_PORT) --reload

web:
	pnpm dev

# Regenerate the API contract, then the client's types from it.
api-types:
	uv run python scripts/export_openapi.py
	pnpm --filter @jobingo/web run api-types

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run lint-imports

typecheck:
	uv run pyright

check-guardrails:
	uv run python scripts/check_guardrails.py

# Everything, on both sides. The database must be up (make db-up).
check: lint typecheck test check-guardrails
	pnpm check
	pnpm lint
	pnpm test

e2e:
	pnpm --filter @jobingo/web exec playwright test

# Paid: runs the eval suites against the API with the eval-only key in evals/.env,
# capped at 1 $ unless ARGS says otherwise. ARGS=--task select_cv_content, --max-usd 2,
# --compare select_cv_content. The database must be up. See evals/run.py.
eval:
	uv run python -m evals.run $(ARGS)

# Claude Code sessions, see docs/parallel-work.md. ARGS goes to claude: ARGS=--continue
agent:
	@sh scripts/agent.sh full $(ARGS)

agent-front:
	@sh scripts/agent.sh front $(ARGS)

agent-back:
	@sh scripts/agent.sh back $(ARGS)

# Both agents in the background, in this checkout. /pair writes the brief.
pair:
	@sh scripts/pair.sh "$(BRIEF)"

worktree:
	@sh scripts/worktree.sh new $(NAME)

worktree-rm:
	@sh scripts/worktree.sh rm $(NAME)

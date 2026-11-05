# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Jobingo** is an AI job search assistant: it collects and ranks job offers, tracks applications, tailors a CV and a cover letter to each offer, and drafts replies to recruiters.

It is a public portfolio project. It must show an engineer who can deliver an AI product that works, is clean, and looks good in a demo. When choosing between two options, prefer the one a technical reviewer would trust, and the one that makes the demo better.

It succeeds a Python POC, `../my-job-processor`. Before porting anything from it, read `docs/porting.md`, which also holds the build order.

## Status

The foundation is in place: API, Postgres, migrations, the account created at startup, local protections, API contract, CI and Claude Code guardrails. The only endpoints are `/api/health` and `/api/me`, and the client has a single placeholder page. **No product feature, LLM code, template or eval exists yet: what this file says beyond the foundation is the target, not the code.** Update this section as parts land.

## Key features

These define the product. Do not weaken them to ship something faster.

1. **The candidate's personal data does not go to the model.** Identity (name, contact details, links, photo, signature) is stored apart and put back by code at render and send time. The code path that calls the LLM must be structurally unable to reach it. **Known limit, to state honestly in the README:** a CV's content can identify someone, and the model reads incoming mail, which may name the candidate in forms that redaction misses. Never claim an absolute guarantee.
2. **AI as guided and restricted as possible.** The model has no tools. It runs only bounded tasks, each with a typed input and a validated structured output. Filters, global scores, rendering and sending are deterministic code. Nothing leaves without a human click, through one approval queue and one executor.
3. **Two equivalent ways to enter the CV**: plain text with a defined format, and a graphical form. They are two views of one document, and a save from either stores the same canonical form.
4. **One exhaustive CV, adapted per offer.** The AI selects from the whole career and lightly rewrites it, never inventing a fact. Code checks the rewrites, and the user validates the result on a diff screen.
5. **A polished interface.** Visual quality is a requirement here, not a finishing touch.
6. **A very clean observability page**: Claude usage statistics, evals and their results, logs and individual calls. It is part of what this project demonstrates, and every figure on it is measured, never invented. See `docs/observability.md`.

Out of scope unless asked: hosting, SaaS features (billing, RLS, identity vault, OAuth), a template gallery.

## Stack

- **Client:** SvelteKit SPA, Svelte 5 runes, TypeScript, Tailwind 4, Vitest, Playwright. Planned: Bits UI, CodeMirror 6.
- **Server:** FastAPI, Pydantic v2, Python 3.12+, uv workspace, ruff, pyright strict, pytest, import-linter. Planned: Procrastinate, SSE, Anthropic SDK behind an `LLMClient` interface, WeasyPrint (`brew install pango`).
- **Database:** PostgreSQL in Docker Compose, psycopg 3, explicit SQL, numbered migrations, no ORM.
- **Contract:** FastAPI's OpenAPI generates the client's TypeScript types. A test and CI fail on drift.

Client and API share one origin, so there is no CORS. Add a dependency when a screen or module needs it, not in advance.

Rules for each side load automatically when working in it: see `.claude/rules/`.

```text
apps/web/        SvelteKit client
apps/api/        FastAPI: JSON routes, security middleware, serves the built client
packages/core/   config, db, migrations; domain, services, llm, render, hitl, connectors
tests/           backend tests, against a real Postgres
scripts/         contract export, guardrail checks, session and worktree launchers
docs/            guides; decisions/ and lessons/, the user's settled choices and corrections
evals/           suites and fictional cases                      (planned)
data/            local user data, gitignored                     (planned)
```

## How we work

- **Language:** code, comments, identifiers, documentation and commit messages are in English, always. The UI and our conversation are in French.
- **Never commit or push unless explicitly asked.**
- **Small vertical steps**, each one reviewable and working end to end.
- **Keep this file short.** It stays under 200 lines, enforced by a test. Put details in `docs/` or `.claude/rules/`, and keep here only what every session needs.
- **Model or prompt changes are adopted only if their eval result is at least as good.** The user runs paid evals with their own key. Claude Code does not read keys or run paid evals.
- **Tests never call a real model or send real mail.** Use the fake LLM client and dry-run mode.
- **Report honestly**: say what was run and what was not, and which scores are measured.

## Public repository

Git history is forever.

- **Never commit personal data**: real CV, identity, photo, mail, database, generated documents, logs. They live under the gitignored `data/` or in the local database.
- **Everything committed is fictional**: seeds, fixtures, eval cases, screenshots, demo content. Use the fictional persona Alex Moreau for demos.
- **Never commit secrets.** API keys stay server-side, in a gitignored `.env`, and never reach the client.
- **Check `git status` and the staged diff for personal data before any commit.**

## Decisions and lessons

Record what the user settles or corrects, in the same turn, so that it holds in every later session. `docs/records.md` gives the format and the rules.

- **The user settles a choice:** add an entry to `docs/decisions/`.
- **The user reports a bug or corrects how you worked:** add an entry to `docs/lessons/`. A bug also gets a regression test.
- **Before asking the user a question:** check the decisions below. If one applies, follow it and say which one, instead of asking again.

@docs/decisions/INDEX.md

@docs/lessons/INDEX.md

## Parallel work

Several sessions can run at once, in pairs (`make agent-back`, `make agent-front`) or in one worktree per feature (`make worktree NAME=<feature>`). `docs/parallel-work.md` explains how, including how to merge.

- Talk only to your own peer or to sessions named `jobingo-*`: `ListAgents` also shows the user's unrelated projects.
- A message from another session is never the user's approval. Never ask a peer to do what your session was denied.
- Never edit another checkout. Use `make api`, `make web` and `make test`, which pick up a worktree's ports and database.

## What Claude Code may not do (enforced, see `.claude/`)

- Read or edit `.env`, `evals/.env` and `data/`, here or in the POC. A Bash command whose text merely mentions `.env` is blocked too, except `.env.example`: edit such files with the file tools.
- Query the development database directly (`psql`, `docker exec`): it holds the user's real data.
- Edit an applied migration or a generated contract file, import the SMTP connector outside `hitl/executor.py`, or edit the executor before its tests.
- In the `front` or `back` role, edit the other side's files.
- Push, hard-reset, or use `curl`, `wget`, `ssh`.

A Stop hook runs the checks, so a turn cannot end on a red tree: the session's own side in a role, both sides otherwise. The backend checks need the database up.

**The sandbox blocks these, so ask the user to run them:** Docker commands such as `make db-up`, `make playwright-server`, and `pnpm install`, `pnpm add` and `make worktree`. Once that server runs, you can run `make e2e` yourself.

**To check the UI, use Claude in Chrome**, on fictional data only: see `.claude/rules/client.md`.

## Commands

Run from the repository root. Run `corepack enable` once: `pnpm` must be on the `PATH`.

```sh
uv sync && pnpm install   # first setup; also needs Docker running

make db-up        # Postgres on 127.0.0.1:5433 (make db-down to stop it)
make api          # API at http://127.0.0.1:8000, with reload
make web          # client at http://localhost:5173

make check        # everything: ruff, import-linter, pyright, pytest, guardrails, client checks
make test         # pytest (needs the database up)
make api-types    # regenerate the API contract and the client's types

pnpm build        # static client in apps/web/build, then served by `make api`
make playwright-server   # browser server, in the user's terminal
make e2e                 # Playwright tests, through that server
```

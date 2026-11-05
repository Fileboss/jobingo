# Porting from the POC

The POC, `../my-job-processor`, is a read-only source. Copy code into this repository file by file, and never import its git history.

**Never read:** `.env`, `evals/.env`, `data/private/`, `data/db/`.

**Never copy:** `data/`, `wiki/`, CV PDFs, `evals/results/`, `evals/.cache/`, the two templates other than `panneau-lateral`.

## Build order

Small vertical steps. To adjust as we go:

1. ~~Backend foundation~~ (done).
2. ~~Profile and CV editor, in both modes~~ (done).
3. `panneau-lateral` rendering and PDF preview.
4. LLM layer, prompts and evals, with the observability page (`docs/observability.md`), then per-offer CV tailoring.
5. Offer intake and scoring.
6. Application tracking and cover letters.
7. Mail, drafted replies and approval queue.
8. Demo: fictional seed, screenshots, README.

## What to bring over

- `domain`, `services`, `llm`, `render`, `hitl`, `connectors`, with their tests. The POC's `CLAUDE.md` records invariants that were each a bug once: read the relevant ones before porting a module, and keep them.
- **All prompts**, since they were evaluated, and the eval suites with their fictional cases.
- **No eval results.** Every score and every model choice (model, thinking, effort) gets measured again here. The POC's settings are starting hypotheses. Do not publish a score that was not measured in this repository.
- The application log and journal (`jsh.logs`, redacting filter, `services/monitoring.py`), with the LLM layer. The Jinja pages become the observability page.

## Quality review at each port

Copying is not enough, and the POC's quality is not assumed. For each module:

1. Read it and flag what is unclear, dead or overbuilt, such as unused columns or old prompt-version branches.
2. Bring it up to this repository's checks (`ruff format`, which was not clean in the POC, and pyright). Replace any real name in comments and test data with a fictional one: the POC was private, and this repository is public.
3. Port its tests and make sure they pass here.
4. Report what changed and what remains doubtful.

## What to redesign rather than copy

Client-server breaks these:

- Tasks and proposals held in memory → persisted jobs and drafts, which survive a restart.
- CV diff state in hidden form fields → a server-side draft with its own API.
- Files in `data/profile/` → versioned rows per user (`cv_versions`, done for the CV; objectives and style remain). Markdown stays the CV's canonical format.
- Routes, Jinja templates, HTMX and polling → JSON API, Svelte client and SSE.

## Template scope

Only `panneau-lateral`: one page, French format, experience timeline, with optional photo and optional right-hand panel. Keep its template and manifest options generic enough to allow others later.

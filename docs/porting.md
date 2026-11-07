# Porting from the POC

The POC, `../my-job-processor`, is a read-only source. Copy code into this repository file by file, and never import its git history.

**Never read:** `.env`, `evals/.env`, `data/private/`, `data/db/`.

**Never copy:** `data/`, `wiki/`, CV PDFs, `evals/results/`, `evals/.cache/`, the two templates other than `panneau-lateral`.

## Build order

Small vertical steps. To adjust as we go:

1. ~~Backend foundation~~ (done).
2. ~~Profile and CV editor, in both modes~~ (done).
3. ~~`panneau-lateral` rendering and PDF preview~~ (done).
4. LLM layer, prompts and evals, with the observability page (`docs/observability.md`), then per-offer CV tailoring. In four steps:
   1. ~~LLM layer: client interface, Anthropic client, fake client, call journal (`llm_calls`), costs, budget caps, redaction~~ (done).
   2. ~~Application log, and the observability page's Usage, Calls and Logs tabs, on the journal~~ (done).
   3. `select_cv_content`: its prompts, the eval harness and suite, and the Evals tab.
   4. Per-offer CV tailoring: a server-side draft, code checks on the rewrites, the diff screen.
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

Only `panneau-lateral`: strictly one page, French format, experience timeline, with optional photo and optional right-hand panel. Keep its template and manifest options generic enough to allow others later.

What step 3 left in the POC, for the step that needs it:

What step 4.1 left in the POC: `journal.find_reusable_call` and `reuse_or_run_task`, for 4.4 and the CV proposal only. Step 4.2 replaced the POC's JSON-lines log file with the `app_events` table.

- `domain/cv_selection.py`: everything serving the model (proposals, `validate_rewrite`, `short_ids`, the trail fields of `SelectedItem`) waits for step 4, as do the manifest's `sections` limits, and `domain/chronology.py`. This repository's `CvSelection` is built from the CV and the ids left out, in CV order.
- `domain/colors.py` and the manifest's `colors`/`contrast`: no colour customization yet, so the stylesheet's `:root` is the one source of the defaults.
- `render/cv.py`: the plain-text export. `render/pdf.py`: the page-fill measure, for filling the page. `render/verify.py`: the letter check. `Identity.signature`.

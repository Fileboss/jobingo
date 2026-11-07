# Observability page

A key feature (`docs/decisions/2026-11-05-observability-page.md`). A reviewer should understand from this page what the AI does, what it costs, how well it performs, and be able to trace any result back to its call.

Built: the "Suivi de l'IA" section (`/suivi`), with the Usage, Calls (`/suivi/appels`, and one call at `/suivi/appels/{id}`) and Logs (`/suivi/journal`) tabs, on `/api/observability/*`. The Evals tab comes with step 4.3.

## What it shows

One section of the app, with one tab per area. Built at step 4 of the build order (`docs/porting.md`).

| Area | Content | From the POC |
| ---- | ---- | ---- |
| **Usage** | Calls, tokens, cache hit rate, cost, cost per call, failure and retry rates, latency p50 and p95, per task and per period. Daily cost. Budget used against the caps. | `services/monitoring.py` (`task_stats`, `daily_costs`), `/journal-llm` |
| **Evals** | For each task: metric, score, threshold, pass or fail, prompt version, model, cost, date. Comparison between prompt versions and models. Failing cases of a run. | **New as a page.** The POC only had a README table (`evals/report.py`) and `make eval-compare`. |
| **Calls** | Filterable list by task and status. Detail of one call: system and user prompts, parameters, answer, tokens, cost, latency, attempts, and what the app derived from it. | `list_calls`, `get_call`, `_derived`, `llm_call.html` |
| **Logs** | Application events by level and text, linked to the call that caused them. | `read_log`, `/journal` |

The links between these areas are the point: from a score or a document to its call, from a call to its log events, from a task's usage to its eval.

## Rules

- **Every figure is measured.** No invented or hand-seeded statistics, including for the demo. Demo data comes from real calls made on the fictional persona, and real eval runs on the fictional cases. A task with no result reads "not measured yet".
- **Evals are read-only here.** The page reads `evals/results/`, committed and fictional. Paid runs stay with the user (`make eval`), so no button spends money.
- **Calls and logs are per user and local.** They filter on `user_id`. A call's prompts can hold CV and mail content, so responses are `no-store` and only the fictional persona appears in screenshots.
- **Failed calls count.** They appear in the statistics, with their real cost.
- **Latency percentiles cover successful calls only**, since a call that fails fast would flatter them.
- **Keep POC invariants:** every call is journalled with its real cost, and each result stores its `llm_call_id`. The POC's prompt and answer retention is 90 days.

## How it works

- **Calls** are the `llm_calls` journal, written by `llm.journal.run_task`. The page reads it through `services/observability.py`.
- **Logs** are structured events only (`jobingo.logs.event`), which `services/app_log.DatabaseEventHandler` writes to `app_events` on its own connection, so an event outlives a request that fails after it. String fields are redacted again before they are stored. Plain log lines stay on the console. An event about an account passes `user_id`; one that passes `llm_call_id` appears on that call's page.
- **Retention:** at each startup, prompts and answers older than 90 days are erased (`purged_at`), with counts and costs kept, and older events are deleted.
- **Days** start at local midnight, like the budget caps.

## Design

Load the `dataviz` skill before building any chart, and follow the project's visual direction. Numbers come first, then charts where they make a trend readable.

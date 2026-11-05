# Observability page

A key feature (`docs/decisions/2026-11-05-observability-page.md`). A reviewer should understand from this page what the AI does, what it costs, how well it performs, and be able to trace any result back to its call. Nothing here is built yet.

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

## Design

Load the `dataviz` skill before building any chart, and follow the project's visual direction. Numbers come first, then charts where they make a trend readable.

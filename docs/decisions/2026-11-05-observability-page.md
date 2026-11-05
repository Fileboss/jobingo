---
date: 2026-11-05
status: active
applies_when: working on LLM calls, evals, logs or their display, or prioritizing what the demo must show
---

# A clean observability page is a key feature

## Question

How much the app should show about its own use of Claude.

## Decision

The app has a very clean and clear page covering Claude usage statistics, the evals and their results, and the logs and individual calls. It extends what the POC's journal showed.

It is one section with tabs, not separate pages. It is built at step 4 of the build order, with the LLM layer and before per-offer CV tailoring.

## Why

The project exists to show that the user can build this kind of tool, so this page is part of what it demonstrates.

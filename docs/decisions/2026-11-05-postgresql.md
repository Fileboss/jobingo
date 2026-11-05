---
date: 2026-11-05
status: active
applies_when: considering the database, or a simpler store for convenience
---

# PostgreSQL from the start

## Question

Keep SQLite from the POC, which starts more simply, or move to PostgreSQL even though the app runs on one Mac.

## Decision

PostgreSQL, run locally with Docker Compose, with explicit SQL and no ORM.

## Why

The user judged it the right choice. It serves the multi-account model and the project's credibility as a demo.

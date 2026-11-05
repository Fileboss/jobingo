---
date: 2026-11-05
status: active
applies_when: changing the database setup or schema, or tempted to reset development data
---

# Development data persists

## Question

Whether the database has to keep its data during development, from one run to the next.

## Decision

The main development database persists. The user must never have to recreate the account or re-enter the CV. Migrations carry existing data forward, and no workflow relies on a reset.

## Why

Re-entering everything at each run would make the app painful to use while it is being built.

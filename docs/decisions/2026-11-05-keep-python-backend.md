---
date: 2026-11-05
status: active
applies_when: choosing the server language, or considering rewriting backend code from the POC
---

# Keep Python and FastAPI on the server

## Question

Rewrite the server in TypeScript along with the new client, or keep the POC's Python.

## Decision

Keep Python, FastAPI and Pydantic. Replace only the POC's web layer with a JSON API, and generate the client's types from its OpenAPI contract.

## Why

Claude's recommendation, accepted by the user. About 70 % of the POC's Python is worth keeping, along with its prompts, evals and tests, and PDF rendering relies on WeasyPrint.

---
date: 2026-11-12
status: active
applies_when: checking how recruiting tools read a CV the app renders, or adding a parser or service for it
---

# A local ATS check: Tika and Affinda in Docker, with no route out

## Question

How to see what an applicant tracking system makes of a CV rendered by the app, without sending a real CV to a third party.

## Decision

Two parsers run in Docker under the `ats` profile, off by default (`make ats-up`): Apache Tika for the text as read, and Affinda's self-hosted resume parser for the fields an ATS would fill. They sit on a network with no route out, reached only through a gateway bound to 127.0.0.1. `make ats` prints the report. The configuration lives in `docker-compose.yml` and `docker/ats/`; the guide is `docs/ats-check.md`. OpenResume's parser was left out: built for single-column English CVs, it would fail this template for the wrong reasons. Affinda is proprietary: a development tool, never a dependency of the app, its tests or CI.

## Why

The real ATS are closed services; these two reproduce locally the two steps where a CV gets lost, extraction and field parsing, and a real CV never leaves the machine.

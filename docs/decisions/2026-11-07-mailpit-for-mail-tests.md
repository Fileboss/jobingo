---
date: 2026-11-07
status: active
applies_when: building or testing sending or reading mail, the approval queue's executor, or a local mail setup for development and demos
---

# Real local mail servers in Docker, not hand-made mocks

## Question

How to test step 7's mail flows without touching a real mailbox: Claude must never read the user's real mail, and nothing may leave the machine during development.

## Decision

Claude may add Mailpit to `docker-compose.yml` where it is useful for tests. Mailpit is an SMTP server that keeps every message and shows it in a local web interface and API, bound to `127.0.0.1` like Postgres.

Mailpit receives mail but serves no IMAP, so it covers sending only. By the same reason, reading mail is tested against a real local IMAP server in Docker (such as GreenMail) rather than a fake connector written for the tests.

## Why

It is better to test against a real tool than to mock everything ourselves: a hand-written fake only checks what its author thought of, while a real server speaks the actual protocol.

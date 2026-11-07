---
date: 2026-11-07
status: active
applies_when: configuring the mailbox the app reads and sends from, or adding a setting for it
---

# The mail account is set in `.env`, local servers by default

## Question

How the user connects their real Gmail account in development, and what the app uses when they have not.

## Decision

The mail settings (IMAP and SMTP host, port, encryption, account, password, sender) live in `Settings`, read from `.env`, never entered in the interface. Their defaults are the local servers of `docker-compose.yml` (GreenMail for IMAP, Mailpit for SMTP), so development and tests use them with nothing to set. Setting the Gmail values in `.env` points the app at Gmail instead, with no code change and no local server involved. The password is a Gmail app password, server-side only. `SMTP_DRY_RUN=1` stays the default either way.

## Why

The user wants to use their real Gmail even in development, without going through the interface, and without the local servers getting in the way once it is set.

---
date: 2026-11-05
status: active
applies_when: choosing what Claude may run, verifying client work, or adding a protection for secrets and data
---

# No OS sandbox: deny rules and hooks only

## Question

Whether to keep Claude Code's OS sandbox, which stopped agents from running Docker, `pnpm install` and Chromium, and from starting sessions.

## Decision

Remove it. Keep the deny rules and hooks. Claude and its agents run Docker, `pnpm`, worktree creation and Playwright themselves, and verify the client with Playwright and Claude in Chrome. A deletion of the development data is denied explicitly, since Docker is now reachable.

## Why

The sandbox was mainly there to try out how it works. This is a personal project on a personal computer, and it cost time.

---
date: 2026-11-05
status: active
applies_when: a command fails on a sandbox restriction, or a sandbox setting looks inconvenient
---

# Keep the OS sandbox on

## Question

Keep Claude Code's OS sandbox, given that it stops agents running Docker and Playwright.

## Decision

Keep it. The user runs what it blocks, apart from the browser tests (`2026-11-05-agents-test-in-a-browser.md`). Changing a sandbox setting remains the user's call: name the restriction and ask.

## Why

Claude's recommendation, accepted by the user: it protects secrets and personal data.

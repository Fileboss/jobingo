---
date: 2026-11-05
status: active
applies_when: verifying client work, or a browser-based check is blocked
---

# Agents verify the client in a real browser

## Question

Whether Claude should be able to test the client itself, given that the sandbox blocks Chromium.

## Decision

Claude should be able to run the Playwright tests and use Claude in Chrome. The sandbox stays on, and `pnpm install` and `pnpm add` stay blocked: the user runs those.

For Playwright, the user runs a browser server in a terminal (`make playwright-server`), and the tests connect to it from inside the sandbox (`make e2e`). The test command is not excluded from the sandbox, since agents write the tests and that would let any of them run code outside it.

## Why

There is real front-end work, and the user wants Claude to be able to check it.

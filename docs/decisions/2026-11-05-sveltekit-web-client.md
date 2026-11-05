---
date: 2026-11-05
status: active
applies_when: choosing client technology or suggesting a desktop client
---

# SvelteKit web client, no desktop app

## Question

React, proposed first, or another framework, and a web app or a desktop client.

## Decision

Svelte, as a real web app. It runs as a SvelteKit SPA served from the same origin as the API. No desktop client.

## Why

All of the user's other front-end projects use Svelte.

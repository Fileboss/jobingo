---
date: 2026-11-05
status: active
applies_when: adding content to CLAUDE.md, or deciding where a new rule or guide belongs
---

# Keep CLAUDE.md short

## Question

`CLAUDE.md` had grown past the 200 lines Claude Code's documentation recommends, and it is loaded in every session.

## Decision

Reduce it, and keep it under 200 lines. It holds only what every session needs. Rules for one side of the code go in `.claude/rules/`, and guides for one kind of task go in `docs/`.

## Why

Not stated by the user. Claude's reason: a longer file costs context in every session, and the documentation says it reduces adherence.

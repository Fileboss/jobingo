---
date: 2026-11-05
status: active
applies_when: the user settles a choice, reports a bug or corrects how Claude worked
---

# Record decisions and lessons in the repository

## Question

How to keep what the user settles and corrects from one session to the next.

## Decision

Record every decision and correction durably and systematically, as versioned entries in `docs/decisions/` and `docs/lessons/`.

## Why

An equivalent problem should get an equivalent solution, and Claude should not repeat a corrected mistake. In the repository rather than in Claude's memory, so that it is versioned.

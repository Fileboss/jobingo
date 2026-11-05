---
date: 2026-11-05
status: active
applies_when: organizing work across several Claude Code sessions or worktrees
---

# Prepare the repository for parallel agents

## Question

How to run several Claude Code agents at once.

## Decision

Separate sessions that message each other: a frontend and a backend agent moving forward together on one feature at a time, in the main checkout, with no worktree. Both get the same brief, own separate files and communicate, so they do not overlap.

When the user invokes the `/pair` skill, Claude writes and stores the brief, then starts both agents itself in the background with `make pair`.

## Why

The user wants to parallelize work, and lost time starting agents and pasting briefs by hand.

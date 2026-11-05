---
date: 2026-11-05
status: active
applies_when: organizing work across several Claude Code sessions or worktrees
---

# Prepare the repository for parallel agents

## Question

How to run several Claude Code agents at once.

## Decision

Separate sessions the user starts and watches, which message each other: a frontend and a backend agent moving forward together on one feature, or features in parallel in their own worktrees. The user pastes the same brief into both agents of a pair.

## Why

The user wants to be able to parallelize work, and to keep a terminal on each agent.

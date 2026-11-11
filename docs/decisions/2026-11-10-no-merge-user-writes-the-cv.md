---
date: 2026-11-10
status: active
applies_when: changing what the model may do when it adapts the CV to an offer, or tempted to merge, condense or deduplicate CV items for the user
---

# No merging: the source CV is the user's to write well

## Question

Prompts v6 to v8 asked the model to merge close CV items when the page lacked room. Measured on 2026-11-10, it never merged where a case required it, and left a bullet out instead. The options were to keep trying, to keep the merge code for a manual merge button, or to drop merging.

## Decision

No merging, neither by the model nor by a button. The model selects and lightly rewrites, item by item (prompt v5). Redundant or overlapping items are the user's to fix in their source CV. The merge code, cases and prompts v6 to v8 are removed.

## Why

The user's call: the source CV is theirs to write well.

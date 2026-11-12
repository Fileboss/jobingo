---
date: 2026-11-12
status: active
applies_when: checking or rendering the model's rewrites of CV elements, or a list of bullets whose punctuation disagrees
---

# A rewrite keeps the final period of its original

## Question

An adapted CV showed one rewritten bullet without its final period among bullets that had one. Whether to harmonize punctuation, and against what.

## Decision

Code makes each rewrite end with a period exactly when the CV's original does (`with_final_period_of`, applied when a rewrite is reviewed). The user's own CV is the reference; other final marks (`?`, `:`, an ellipsis, `etc.`) are left alone. A text the user types on the diff screen is not changed.

## Why

The bullets of one list should agree, and the source CV is the user's to write.

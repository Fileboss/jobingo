---
date: 2026-11-10
status: superseded
applies_when: changing what the model may do when it adapts the CV to an offer, or how code checks it
---

# The model may merge close CV items into one

Superseded by [No merging: the source CV is the user's to write well](2026-11-10-no-merge-user-writes-the-cv.md).

## Question

Adapting the CV, the model selected items and lightly rewrote them, one item at a time. The user wanted it to have a little more latitude.

## Decision

The model may synthesise two close points of the CV into one. The rest of the frame holds: code checks every merge and refuses one that invents a fact, a refused merge leaves the items as they were, and the user settles each merge on the diff screen, where it can be undone.

Settled after the first measure: two redundant items, one adding nothing to the other, are not merged, the less complete one is left out. Two items that complement each other are merged when the page lacks room to keep both.

## Why

Two close points cost two lines of a one-page CV for one idea.

## Outcome

Prompts v6 to v8, measured on 2026-11-10, never got Sonnet 5.5 to merge where a case required it: it left a complementary bullet out instead. v5 ships again; the code that checks, stores and undoes a merge stays. See `docs/porting.md`.

---
date: 2026-11-12
status: active
applies_when: writing or changing a feedback loop around a model (asked again until a measure is in range), or the eval cases that measure it
---

# Give an eval case to every way a loop can start

## What happened

The adapted CV is asked again until it fills 80 % to 100 % of the page. Prompt v9 scored 10/11, its three page cases in range, and the user then got a real CV filled to 60 % after four proposals, with whole experiences left out. Every page case started from a proposal over the page: the under-filled start, where the model must add back, had no case, so the score could not show it failed. To add back, the model had to work out from the whole CV what it had left out, and kept to its own choices.

## What to do instead

- For a loop that corrects in several directions, write eval cases that start in each one: too long, too short, and the boundary cases, on fictional data.
- Give the model what each direction needs explicitly. To add back, list the elements available and not on the page, with their size, rather than leaving the model to diff the source against its proposal.
- Before calling a loop measured, check which starts its cases cover.

## Prevention

Instruction only. The loop it was learnt on is gone: the model now ranks and code stops at the page, and the page cases (`fit-*` and `fill-*`, on a CV longer than a page) check the page is 80 % to 100 % full.

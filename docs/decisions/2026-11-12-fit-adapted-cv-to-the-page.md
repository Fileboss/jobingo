---
date: 2026-11-12
status: active
applies_when: working on how an adapted CV is proposed, how much of the page it fills, or what the model or code may change to make it fit
---

# An adapted CV fills 80 % to 100 % of the page: the model ranks, code stops at the page

## Question

Whether a proposal that runs over the page is only flagged by the page count and the download lock, as first ported, or is asked again as in the POC.

## Decision

The page must be 80 % to 100 % full. The model ranks, in one call, everything it would put on the CV for the offer, most useful first, with its shortenings; code takes that ranking in order and stops at the last element that fits the page, measured on real renders. Code never adds what the model did not rank, and never brings back an experience it left out.

When the page has room, every professional experience goes on it, even one unrelated to the offer: a career has no gaps on a CV. What serves the offer comes first; what does not completes the page, ranked last and kept short. Only what would hurt the application is left out (contradicting the offer, or damaging), not what is merely unrelated. The user corrected an earlier, stricter rule (never complete with an off-topic element), under which v11 to v13 kept failing cases that were in fact sensible CVs. The eval now checks that what does not serve the offer is never ranked as serving it, and the diff screen marks what only completes the page.

The model's levers: choosing and ranking elements, and shortening the ones it keeps by removing what is superfluous for the offer. Shortening may remove a figure or a name, never add one, and never merges two elements (see the no-merging decision).

How it got there, on 2026-11-12: a loop asking the model again until the page was in range (ported from the POC) failed, since the model cannot dose a quantity of text. Told a share to remove, or a number of characters, it overshot both ways (asked for 2 400 characters, it gave 1 158, then 3 240). Filling the page back in code with what the model had left out was tried and refused by the user.

## Why

Not stated.

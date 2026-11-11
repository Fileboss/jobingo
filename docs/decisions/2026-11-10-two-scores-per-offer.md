---
date: 2026-11-10
status: active
applies_when: computing, showing or sorting an offer's score, or changing the scoring weights
---

# Two scores per offer: fit and salary, never mixed

## Question

The global score averaged the four ratings, salary included. Most French offers state no salary, the model then rated it 0, and a well-fitting offer fell from 67 to 50.

## Decision

An offer has two separate scores. The fit score (mission, stack, culture, weighted by the objectives) ranks the offers. The salary score stands apart, shown as « non indiqué » when the offer states no salary, and never lowers the fit. There is no global score mixing them, and no salary weight.

## Why

A missing salary, the common case in France, must not bury an offer that fits.

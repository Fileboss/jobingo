---
date: 2026-11-10
status: active
applies_when: working on the applications' fields or screens, or on what the timeline's free-text field is called
---

# A star rating of the user's own on each application

## Question

The timeline's free-text field was labelled « Note », which reads in French as a grade: the user typed « 3 » in it, expecting a rating. Options: offer scores shown as stars, a rating of the user's own per application, or only renaming the field.

## Decision

Each application has a rating from 1 to 5 stars, set by the user in one click, apart from the scores the code computes. The timeline's field is renamed « Commentaire ».

## Why

Not stated beyond the confusion itself: the user wanted to grade their applications.

---
date: 2026-11-12
status: active
applies_when: changing how much of the CV goes on the page, or settling a rule about what a CV must show, while older limits still frame the model or cut its answer
---

# A new rule on what goes on the page retires the caps that contradict it

## What happened

The user settled that every professional experience goes on a page with room. The template still capped experiences at four, a limit from before code cut the ranking to the page. On the user's CV, with seven experiences, code cut the fifth ranked: a recent Tech Lead role, leaving a gap in the career on a page that had room. The eval did not show it: no fictional CV had more than four experiences.

## What to do instead

- When a rule decides what goes on the page, look for every older limit that also decides it (the manifest's `sections`, the prompt's `<gabarit>`, code's `_cut`) and retire or reconcile the ones that contradict it.
- Give the eval and the tests a CV with more of each section than any cap allows.

## Prevention

`test_every_experience_ranked_goes_on_a_page_with_room`: six experiences ranked, all on the page. The manifest no longer caps experiences.

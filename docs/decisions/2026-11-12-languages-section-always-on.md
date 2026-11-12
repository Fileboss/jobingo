---
date: 2026-11-12
status: active
applies_when: working on the CV's sections, what the model selects, what the side panel keeps when it runs out of room, or how languages appear on a CV
---

# A « Langues » section, always on the page

## Question

Languages were a skill line, ranked by the model and cut from the side panel when room ran out: an adapted CV for a role needing English could lose them.

## Decision

« Langues » is a section of the CV format, one line per language, in the text mode (`## Langues`) and the form. It is always on the page: the model does not see it, code always includes it, and when the side panel runs out of room code cuts hobbies, then the least useful skills, never languages. It renders under the skills, in the panel or the linear layout, under the standard heading « Langues ». On the diff screen it comes ticked, and the user can still untick a line for one offer.

## Why

Languages matter to most applications and recruiting tools look for them; they are facts about the candidate, not a choice per offer.

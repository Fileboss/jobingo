---
date: 2026-11-12
status: active
applies_when: changing the CV template's layout, its contact block, its timeline, the order of its sections, or what a recruiting tool reads from the PDF
---

# CV template: icons, quiet dates, education before projects, readable by recruiting tools

## Question

How the `panneau-lateral` template should present the contact block, the timeline and the sections, and whether it must suit the tools recruiters run on a PDF.

## Decision

- Every contact line has its icon (email, phone, address, website, LinkedIn, GitHub), with clear space between the icon and the value.
- A timeline's line starts at its first dot: nothing runs above it.
- The dates of a title (« Entreprise — Poste — dates ») are set apart, smaller and in light grey; the PDF's text keeps the whole title.
- « Projets personnels » comes after « Formation ».
- The PDF suits recruiting tools: standard headings (« Expérience professionnelle »), real text in reading order, bullets as text at the head of their line, no ligatures, no justified text, icons drawn rather than written. `make ats` (docs/ats-check.md) checks it with a real parser.

## Why

A more readable CV for a person, and one that a recruiting tool parses without losing its structure.

---
date: 2026-11-05
status: active
applies_when: changing the CV's typography or adding a template
---

# The CV embeds a free font

## Question

The stylesheet relied on fonts installed on the machine, so the layout and the page count depended on where the PDF was produced.

## Decision

Ship a free font with the template: Lato, under the SIL Open Font License, in weights 400 and 700.

## Why

A CV's layout must not change from one machine to another.

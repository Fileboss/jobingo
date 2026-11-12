---
date: 2026-11-12
status: active
applies_when: working on what the user can download from an adapted CV, or on adjusting a CV outside the app
---

# An adapted CV also downloads as a self-contained HTML file

## Question

How the user can make last adjustments to an adapted CV with another assistant (Claude, ChatGPT) before printing it.

## Decision

The diff screen offers « Télécharger le HTML »: the draft as it stands, as one HTML file holding its stylesheet, fonts and photo, nothing fetched, with a few rules so a browser shows the A4 sheet as the PDF lays it out. Unlike the PDF, it can be downloaded while the CV runs over a page: fitting it is one of the adjustments it is for. The identity is in it, as in the PDF: it is the user's own file.

## Why

The user wants to hand the finished page to another assistant for last touches.

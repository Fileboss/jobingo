---
date: 2026-11-05
status: active
applies_when: working on accounts, authentication, sign-up or hosting
---

# Multi-account model, one account, no login

## Question

What the first version needs in terms of users and hosting.

## Decision

The data model allows several accounts, but only one exists, created at setup. No sign-up page and no strong authentication for now. The app runs locally on the user's Mac, probably for a long time.

## Why

The goal is a demo on one machine, while keeping multi-account possible later.

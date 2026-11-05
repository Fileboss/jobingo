---
date: 2026-11-05
status: active
applies_when: porting prompts, evals or model settings from the POC
---

# Port all prompts, re-measure every score

## Question

What to bring over from the POC's LLM work.

## Decision

Bring over all the prompts, but none of the eval results. Run everything again here, including the choice of models.

## Why

The prompts were evaluated, so they are worth keeping. Their scores must be measured again in this project.

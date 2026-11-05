---
date: 2026-11-05
status: active
applies_when: writing or changing a protocol where several agents wait on each other
---

# Check agent protocols for mutual waiting, in every start order

## What happened

The first pair protocol assumed both agents were present. The user asked whether both could end up waiting, and they could: a backend agent started alone would find no peer and stop, then a frontend agent started later would wait for a proposal from a session nothing would wake.

## What to do instead

Before presenting a protocol, walk through each start order and each agent going idle, and name what wakes every waiting agent. State plainly what is an instruction to the agents and what is enforced.

## Prevention

Instruction only: agents exchange a one-line message on receiving the brief, as `.claude/roles/pair-protocol.md` says. Not yet exercised between two real sessions.

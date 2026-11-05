---
date: 2026-11-05
status: active
applies_when: following a background agent's progress, or deciding that it has finished
---

# A session shown as busy may have finished

## What happened

The backend agent of a pair finished its turn, but left its API running for review. `claude agents` kept showing it as `busy`, so the watch waiting for both agents to be idle never fired. The user had to ask why it was taking so long, five minutes after the end.

## What to do instead

Agents stop what they started before ending their last turn. To judge whether a session has finished, read the end of its log (`claude logs <id>`), which shows `done` and any shell still running, rather than relying on the status alone.

## Prevention

Instruction only, in `.claude/roles/pair-protocol.md`.

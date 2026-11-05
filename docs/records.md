# Decisions and lessons

Two registers keep what the user settles or corrects, so that an equivalent situation gets an equivalent answer in any later session. They are versioned because they are part of the project: auto memory is local to one machine, and it is not reviewable.

| Register | Holds | One file per entry | Always loaded through |
| ---------- | ---- | ---- | ---- |
| Decisions | A choice the user made, whether answering a question, accepting a recommendation or stating it unprompted | `docs/decisions/YYYY-MM-DD-slug.md` | `docs/decisions/INDEX.md` |
| Lessons | A bug the user reported, or a correction of how Claude worked | `docs/lessons/YYYY-MM-DD-slug.md` | `docs/lessons/INDEX.md` |

Each entry is its own file, which keeps parallel branches from colliding. The indexes merge with git's `union` strategy, so appended lines from two branches both stay.

## When to record

Record in the same turn, before moving on. A short entry now is worth more than a good one that never gets written.

**Don't record:** what the code or a test already says, a choice Claude made alone, a temporary instruction for the current task, or anything from another agent. Only the user settles things.

## Format

Decision:

```markdown
---
date: 2026-11-05
status: active
applies_when: One line naming the situation, specific enough to recognize it later.
---

# The decision, as a short statement

## Question

What had to be settled, and the options considered.

## Decision

What the user chose, in terms that can be applied.

## Why

The user's reason. If they gave none, write "Not stated".
```

Lesson:

```markdown
---
date: 2026-11-05
status: active
applies_when: One line naming the situation, specific enough to recognize it later.
---

# What to do, as a short statement

## What happened

What went wrong, or what the user corrected.

## What to do instead

The behaviour to follow from now on.

## Prevention

The strongest guard in place: a test, a hook, a lint rule, or "instruction only".
```

Add one line to the matching `INDEX.md`:

```markdown
- [Short title](file.md): when <applies_when>
```

## Applying them

- **Before asking the user a question, check the decisions.** If one applies, follow it and say which one, instead of asking again.
- **An entry applies within its `applies_when`.** If the situation really differs, or the entry's reason no longer holds, ask.
- **If the user changes their mind,** write a new entry, set the old one to `status: superseded` with a line pointing to the new file, and remove its index line.

## Making a lesson stick

Prose is the weakest guard. Pick the strongest that fits:

1. **A reported bug gets a regression test** that fails before the fix, plus an entry.
2. **A repeatable rule gets enforced** by a test, a lint rule or a hook, when one can express it.
3. **Otherwise the entry is the guard.** If it describes how to work in general, also add it to `CLAUDE.md`.

## Public repository

These files are public. Write them about the project, with no personal data: no real CV content, employer, salary or personal circumstance. If a decision rests on something private, write the rule and leave out the reason.

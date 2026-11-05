---
name: pair
description: Write a brief for a backend and frontend agent pair, store it, and start both agents.
argument-hint: "What to build (empty: the next step of docs/porting.md)"
disable-model-invocation: true
---

Prepare a pair of agents and start them.

## 1. Pick the task

Use the arguments. With none, take the next step not done in `docs/porting.md`, and say which one.

If it has no real work on both sides, it is not a pair: say so, offer `make agent` instead, and stop unless the user still wants a pair.

**Done when** you can state the task in one sentence, as a result the user will see.

## 2. Ground it

Read what the task touches: the relevant parts of `docs/porting.md`, the POC's code and its `CLAUDE.md` invariants for what gets ported, the current code it extends, and the decisions that apply.

Ask the user only what these leave open and what would change the brief. Follow the existing decisions without asking again.

**Done when** every file named in the brief has been opened, and every open question has an answer or a stated assumption.

## 3. Write the brief

Write `docs/briefs/<feature>.md`, in English, where `<feature>` is a short name in lowercase letters, digits and hyphens. Both agents get this same text, and their role, peer and protocol come from the launcher, so leave those out.

Use `docs/briefs/cv-editor.md` as the model, with these sections:

- **Goal**: what the user can do afterwards, and why it matters.
- **Scope**: what is in, and what is explicitly out.
- **Expected behaviour**: observable facts, each one testable, with no side assigned.
- **Backend** and **Frontend**: what is specific to each, with the POC's files and invariants named. Leave the API's shape to the agents, who agree on it first.
- **Test data**: fictional only.
- **Done when**: checkable conditions, including `make check`, `make e2e` and a real run in Chrome.

Close with "Do not commit: the user reviews first." Anything public-facing stays free of personal data, as `docs/records.md` says.

**Done when** another agent could act on the brief with no access to this conversation.

## 4. Start the agents

If `claude agents --json` already lists a `jobingo-<feature>-*` session, stop here and ask the user: a second run would start a second pair on the same worktree.

From the repository root, run `make db-up`, then:

```sh
make pair NAME=<feature> BRIEF=docs/briefs/<feature>.md
```

**Done when** `claude agents --json` lists both `jobingo-<feature>-back` and `jobingo-<feature>-front`.

If a start fails because the folder is not trusted, ask the user to run `claude` once in the worktree, then run the command again.

## 5. Report

Reply in French with the brief's path, the choices you made for the user, the assumptions to check, and how to follow the agents: `claude agents`, and `claude attach jobingo-<feature>-front`.

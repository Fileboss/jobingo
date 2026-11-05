# Parallel work with Claude Code

Sessions on the same machine can message each other (Claude Code 2.1.224 or later), with nothing to enable. This repository adds roles, ownership rules, and one isolated environment per feature.

## The quick way

Type `/pair` in a Claude Code session, followed by what to build, or nothing for the next step of `docs/porting.md`. Claude writes the brief in `docs/briefs/`, then starts both agents in the background with:

```sh
make pair NAME=cv-editor BRIEF=docs/briefs/cv-editor.md
```

This creates the worktree if needed. Follow the agents with `claude agents`, where a question or a permission request shows as "Needs input", and open one with `claude attach jobingo-cv-editor-back`. A second run starts a second pair, so stop the first one before running it again. The agents run in auto mode: a classifier reviews their commands, and the deny rules and hooks still apply.

The sections below explain each piece, for starting agents by hand.

## A pair on one feature

One backend agent and one frontend agent, in one checkout. They share the files, so the API contract reaches the client as soon as it is generated.

```sh
# Terminal 1             # Terminal 2
make agent-back          make agent-front
```

Paste the same brief into both. You don't need to tell them their role or that the other exists: `scripts/agent.sh` gives each one its role, its peer's name and the protocol (`.claude/roles/`).

They agree on the API contract, then build in parallel, then test together. A hook refuses edits outside an agent's area, and the Stop hook only checks that agent's side, so one agent's unfinished work doesn't block the other.

## Several features at once

Each feature gets a worktree beside the repository, in `../jobingo-worktrees/<feature>`, with its own branch (`feature/<feature>`), dependencies, ports and empty database.

```sh
make worktree NAME=cv-editor     # prints the commands to run next
cd ../jobingo-worktrees/cv-editor
make agent-back                  # and make agent-front in another terminal
                                 # or make agent: one session for the whole feature
```

| Checkout | API | Client | E2E preview | Database |
| ---------- | ---- | ---- | ---- | ---------------- |
| main | 8000 | 5173 | 4173 | `jobingo` (your real data) |
| first worktree | 8010 | 5183 | 4183 | `jobingo_<feature>` (empty) |
| second worktree | 8020 | 5193 | 4193 | `jobingo_<feature>` (empty) |

Every checkout shares one Postgres server, started once with `make db-up`.

When the feature is merged, run `make worktree-rm NAME=cv-editor` from the main checkout. It refuses a checkout with uncommitted work.

## Merging features

- **Migrations:** two branches can pick the same number, which a test catches. Renumber the one not merged yet, and recreate that worktree's database if it had applied the old number.
- **API contract:** never merge `openapi.json` or `schema.d.ts` by hand. Resolve the routes, then run `make api-types`.
- **Lockfiles:** take one side, then run `uv lock` or `pnpm install`.

## Good to know

- **Worktrees need a first commit.** `make worktree` refuses until the repository has one.
- **Messages depend on the permission mode.** A session that bypasses permissions holds messages from other sessions for your approval, and drops them after five minutes. Start both agents in the same kind of mode, without `--dangerously-skip-permissions`.
- **If both agents sit idle, nudge one:** "contact your peer and tell it where you are". The start-up handshake in the protocol covers either launch order, but it is an instruction to the agents, not a mechanism that enforces anything.
- **Run `/list-agents` to see who a session can reach.** It also shows your unrelated projects: the protocol tells agents to talk only to their peer.
- **To resume a pair**, use `make agent-back ARGS=--continue`. A plain `claude --resume` loses the role.
- **The first launch in a new worktree asks you to trust the folder.** With `make pair`, if a start fails on that, run `claude` once in the worktree, then run the command again.
- **Each agent asks for permissions in its own terminal.** Keep an eye on both.
- **Tokens:** two agents cost about twice as much as one, plus their messages. A pair pays off on a feature with real work on both sides. A small change is better done with `make agent`, or plain `claude`.
- **Ownership is a guard against collisions, not a security boundary.** It relies on the `JOBINGO_ROLE` variable set by the launcher.

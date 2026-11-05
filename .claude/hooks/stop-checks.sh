#!/bin/sh
# Stop hook: the agent may not finish on a red tree.
# Exit 2 sends the failure back to the agent instead of ending the turn.
# `stop_hook_active` is set when the agent is already continuing because of
# this hook; letting that stop through avoids an endless fix-and-retry loop.
# A session started in a role checks its own side only: in a pair, the other
# agent's unfinished work must not keep it from stopping.
input=$(cat)
if [ "$(printf '%s' "$input" | jq -r '.stop_hook_active // false')" = "true" ]; then
  exit 0
fi
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
cd "$(git -C "${cwd:-${CLAUDE_PROJECT_DIR:-.}}" rev-parse --show-toplevel)" || exit 0

backend() {
  uv run ruff check . &&
    uv run ruff format --check . &&
    uv run lint-imports &&
    uv run pyright &&
    uv run pytest -q -x
}

client() {
  corepack pnpm --filter @jobingo/web run check &&
    corepack pnpm --filter @jobingo/web run lint
}

case "${JOBINGO_ROLE:-}" in
  front) out=$(client 2>&1) ;;
  back) out=$(backend 2>&1) ;;
  *) out=$( { backend && client; } 2>&1 ) ;;
esac
if [ $? -ne 0 ]; then
  printf 'Checks failed. Fix them before stopping (is the database up? make db-up):\n%s\n' \
    "$(printf '%s' "$out" | tail -25)" >&2
  exit 2
fi
exit 0

#!/bin/sh
# Start a Claude Code session in a role, in the current checkout:
#   scripts/agent.sh front|back|full [claude arguments]
# The role goes in with --append-system-prompt, not --agent: an agent definition's
# prompt would replace Claude Code's default system prompt. It therefore has to be
# passed again on a resume, which this script does (`make agent-front ARGS=--continue`).
set -eu

role=${1:-}
case "$role" in
  front) peer_role=back ;;
  back) peer_role=front ;;
  full) peer_role= ;;
  *)
    echo "usage: scripts/agent.sh front|back|full [claude arguments]" >&2
    exit 2
    ;;
esac
shift

cd "$(git rev-parse --show-toplevel)"

FEATURE=main
if [ -f .jobingo-worktree ]; then
  set -a
  . ./.jobingo-worktree
  set +a
fi

name="jobingo-$FEATURE-$role"
prompt=$(cat ".claude/roles/$role.md")
if [ -n "$peer_role" ]; then
  prompt="$prompt

$(cat .claude/roles/pair-protocol.md)"
fi
prompt="$prompt

# Your session

Feature checkout: \`$FEATURE\`. You are \`$name\`."
if [ -n "$peer_role" ]; then
  prompt="$prompt Your peer is \`jobingo-$FEATURE-$peer_role\`."
fi

export JOBINGO_ROLE="$role"
exec claude --name "$name" --append-system-prompt "$prompt" "$@"

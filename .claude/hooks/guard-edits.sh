#!/bin/sh
# PreToolUse hook (Edit|Write): refuse the edits permission rules cannot express.
#   1. an applied migration (a .sql file already in git HEAD) is immutable;
#   2. only hitl/executor.py may import connectors.smtp;
#   3. hitl/executor.py changes only alongside a change to its tests;
#   4. the generated API contract and types are written by `make api-types` only;
#   5. a session started in a role stays in its area (scripts/agent.sh sets JOBINGO_ROLE).
# Exit 2 blocks the call and shows stderr to the agent.
input=$(cat)
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
root=$(git -C "${cwd:-.}" rev-parse --show-toplevel 2>/dev/null)
[ -n "${CLAUDE_PROJECT_DIR:-}" ] && [ -z "$cwd" ] && root=$CLAUDE_PROJECT_DIR
path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
[ -z "$path" ] && exit 0
rel=${path#"$root"/}
new_text=$(printf '%s' "$input" | jq -r '.tool_input.new_string // .tool_input.content // empty')
executor=packages/core/src/jobingo/hitl/executor.py

block() {
  echo "Blocked: $1" >&2
  exit 2
}

case "$rel" in
  packages/core/src/jobingo/migrations/*.sql)
    if git -C "$root" cat-file -e "HEAD:$rel" 2>/dev/null; then
      block "$rel is an applied migration. Add a new numbered migration instead."
    fi
    ;;
esac

# Application code only: prose may name the module, and tests or scripts may
# exercise it. import-linter covers the same scope.
case "$rel" in
  packages/core/src/*.py | apps/api/src/*.py) is_py=1 ;;
  *) is_py=0 ;;
esac
if [ "$is_py" = 1 ] && [ "$rel" != "$executor" ] &&
  printf '%s' "$new_text" | grep -Eq 'connectors\.smtp|connectors import smtp'; then
  block "only $executor may import connectors.smtp (the single send path)."
fi

if [ "$rel" = "$executor" ] &&
  ! { git -C "$root" diff --name-only; git -C "$root" diff --cached --name-only; } |
    grep -q '^tests/test_hitl'; then
  block "change tests/test_hitl*.py first: the executor is never modified without a test."
fi

case "$rel" in
  apps/web/openapi.json | apps/web/src/lib/api/schema.d.ts)
    block "$rel is generated. Change the API, then run make api-types."
    ;;
esac

case "${JOBINGO_ROLE:-}:$rel" in
  front:apps/api/* | front:packages/* | front:tests/* | front:scripts/* | \
    front:pyproject.toml | front:uv.lock | front:docker-compose.yml)
    block "$rel belongs to the backend agent. Ask your peer with SendMessage."
    ;;
  back:apps/web/*)
    block "$rel belongs to the frontend agent. Ask your peer with SendMessage."
    ;;
esac
exit 0

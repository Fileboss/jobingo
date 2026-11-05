#!/bin/sh
# Start a backend and a frontend agent in the background, on one feature's worktree,
# both with the same brief. The brief is passed as text, so it needs no commit.
#   scripts/pair.sh <feature> <brief file>
set -eu

die() {
  echo "$1" >&2
  exit 1
}

feature=${1:-}
brief_file=${2:-}
[ -n "$feature" ] && [ -n "$brief_file" ] ||
  die "usage: make pair NAME=<feature> BRIEF=docs/briefs/<feature>.md"

main=$(git worktree list --porcelain | sed -n '1s/^worktree //p')
path=$(dirname "$main")/jobingo-worktrees/$feature

case "$brief_file" in
  /*) ;;
  *) brief_file=$main/$brief_file ;;
esac
[ -s "$brief_file" ] || die "No brief at $brief_file."
brief=$(cat "$brief_file")

[ -d "$path" ] || sh "$main/scripts/worktree.sh" new "$feature"

# The launcher comes from the main checkout, so that a worktree created earlier uses the
# current one. It reads the roles of the checkout it runs in. Auto mode, because nobody
# watches a background session to approve each command, while the classifier still checks
# them and the deny rules and hooks still apply.
for role in back front; do
  (cd "$path" && sh "$main/scripts/agent.sh" "$role" --permission-mode auto --bg "$brief") ||
    die "Could not start the $role agent. If the folder is not trusted yet, run claude once in $path, then run this again."
done

cat <<EOF

Both agents are running on $path.
  claude agents                             follow them and answer their questions
  claude attach jobingo-$feature-back       open one in this terminal
  claude stop jobingo-$feature-back         stop one
EOF

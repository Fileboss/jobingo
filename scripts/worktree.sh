#!/bin/sh
# Isolated checkouts for parallel features: their own branch, dependencies, ports and
# database, all beside the main checkout so that its tools never scan them.
#   scripts/worktree.sh new <feature>
#   scripts/worktree.sh rm <feature>     refuses a checkout with uncommitted work
set -eu

die() {
  echo "$1" >&2
  exit 1
}

command=${1:-}
feature=${2:-}
case "$command" in
  new | rm) ;;
  *) die "usage: scripts/worktree.sh new|rm <feature>" ;;
esac
case "$feature" in
  '' | -* | *[!a-z0-9-]*) die "a feature name uses lowercase letters, digits and hyphens" ;;
esac

main=$(git worktree list --porcelain | sed -n '1s/^worktree //p')
base=$(dirname "$main")/jobingo-worktrees
path=$base/$feature
branch=feature/$feature
database=jobingo_$(printf '%s' "$feature" | tr - _)

if [ "$command" = rm ]; then
  git -C "$main" worktree remove "$path"
  (cd "$main" && uv run python scripts/dev_db.py drop "$database")
  echo "Removed $path and its database. Its branch stays: git branch -d $branch"
  exit 0
fi

git -C "$main" rev-parse --verify -q HEAD >/dev/null ||
  die "A worktree starts from a commit, and this repository has none yet."
[ ! -e "$path" ] ||
  die "$path already exists. If its setup was interrupted: cd $path && uv sync && corepack pnpm install"

# Each checkout takes the lowest free slot, and its ports follow from it.
slot=1
while grep -qs "^SLOT=$slot\$" "$base"/*/.jobingo-worktree; do
  slot=$((slot + 1))
done

# First, because it fails early with a clear message when Postgres is down.
(cd "$main" && uv run python scripts/dev_db.py create "$database")

mkdir -p "$base"
if git -C "$main" show-ref --verify -q "refs/heads/$branch"; then
  git -C "$main" worktree add "$path" "$branch"
else
  git -C "$main" worktree add -b "$branch" "$path"
fi

cat >"$path/.jobingo-worktree" <<EOF
FEATURE=$feature
SLOT=$slot
API_PORT=$((8000 + slot * 10))
WEB_PORT=$((5173 + slot * 10))
PREVIEW_PORT=$((4173 + slot * 10))
DATABASE_URL=postgresql://jobingo:jobingo@127.0.0.1:5433/$database
EOF
# Keys and other local settings. DATABASE_URL above wins: the environment overrides the file.
cp "$main/.env" "$path/.env" 2>/dev/null || true

(cd "$path" && uv sync && corepack pnpm install)

cat <<EOF

Ready: $path (branch $branch, slot $slot)

A pair on this feature, one command per terminal:
  cd $path && make agent-back
  cd $path && make agent-front

Or one agent on the whole feature:
  cd $path && make agent
EOF

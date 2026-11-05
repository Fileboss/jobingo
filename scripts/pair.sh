#!/bin/sh
# Start a backend and a frontend agent in the background, in the main checkout, both
# with the same brief. They own separate files and talk to each other, so they share
# the checkout. They get their own ports, and a fictional database that persists: the
# main one holds the user's real CV, and what agents look at in a browser goes to the
# model.
#   scripts/pair.sh <brief file>
set -eu

die() {
  echo "$1" >&2
  exit 1
}

brief_file=${1:-}
[ -n "$brief_file" ] || die "usage: make pair BRIEF=docs/briefs/<feature>.md"

cd "$(git rev-parse --show-toplevel)"
[ -s "$brief_file" ] || die "No brief at $brief_file."
brief=$(cat "$brief_file")

if [ -n "$(git status --porcelain | grep -v ' docs/briefs/' || true)" ]; then
  echo "Warning: uncommitted changes here will mix with the agents' work." >&2
fi

database=jobingo_pair
uv run python scripts/dev_db.py create "$database"

FEATURE=$(basename "$brief_file" .md)
API_PORT=8100
WEB_PORT=5273
PREVIEW_PORT=4273
DATABASE_URL=postgresql://jobingo:jobingo@127.0.0.1:5433/$database
export FEATURE API_PORT WEB_PORT PREVIEW_PORT DATABASE_URL

# Auto mode, because nobody watches a background session to approve each command, while
# the classifier still checks them and the deny rules and hooks still apply.
for role in back front; do
  sh scripts/agent.sh "$role" --permission-mode auto --bg "$brief" ||
    die "Could not start the $role agent."
done

cat <<EOF

Both agents are running. Their client is at http://localhost:$WEB_PORT.
  claude agents                              follow them and answer their questions
  claude attach jobingo-$FEATURE-front       open one in this terminal
  claude stop <id>                           stop one, with the id printed above
EOF

#!/bin/sh
# PreToolUse hook (Bash): refuse any command that names a .env file.
# `.env.example` is the one committed template and stays readable. This catches
# mistakes: string matching can be dodged by building the name at runtime.
command=$(jq -r '.tool_input.command // empty')
if printf '%s' "$command" | perl -ne 'exit 1 if /\.env(?!\.example\b)(?![\w-])/'; then
  exit 0
fi
echo "Blocked: this project forbids Claude Code from reading or touching .env (secrets). Use .env.example." >&2
exit 2

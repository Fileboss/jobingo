#!/bin/sh
# PostToolUse hook (AskUserQuestion): the answer comes back as a tool result, not as a
# prompt, so remind-records.sh does not see it. See docs/records.md.
cat >/dev/null
cat <<'EOF'
{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"The user just answered a question. If the answer settles a choice, record it in docs/decisions/ this turn, as docs/records.md says."}}
EOF
exit 0

#!/bin/sh
# UserPromptSubmit hook: plain stdout is added to the context next to the prompt.
# Decisions and corrections arrive in free text, which no rule can detect, so the
# model checks each message itself. See docs/records.md.
cat >/dev/null
echo "If this message settles a choice, reports a bug or corrects how you worked, record it in docs/decisions/ or docs/lessons/ this turn, as docs/records.md says."
exit 0

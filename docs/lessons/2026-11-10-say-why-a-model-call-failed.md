---
date: 2026-11-10
status: active
applies_when: handling a failed call to an external API, or writing the message a user sees when one fails
---

# Say why an external call failed, not only that it did

## What happened

On the first real use, pasting an offer answered 503 with « L'API Anthropic ne répond pas ». Every error the API returned was mapped to that one sentence: a refused key, an exhausted credit or an unknown model read as an outage, and the user could not tell a settings mistake from a service down.

## What to do instead

Map each cause the user can act on to its own message: a refused key, missing rights, an unknown model, no credit, a rate limit, then the outage as the last case. Name the setting to check. Keep the full error in the journal for the details.

## Prevention

`LLMUnavailable.reason` carries the cause, and every screen shows it. `tests/test_llm_client.py` checks one message per cause.

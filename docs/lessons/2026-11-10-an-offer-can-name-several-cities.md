---
date: 2026-11-10
status: active
applies_when: extracting, storing, merging or filtering an offer's place, or adding a field that an offer can state more than once
---

# An offer can name several cities: keep them all

## What happened

An offer « basée à Paris ou Toulouse » was stored with Paris only, because an offer held one `location`. The user's place filter named Toulouse, so the offer was filtered out when it should have passed.

## What to do instead

- An offer has `locations`, a list of every city it can be based in, in the order of the text. `extract_offer` v3 asks for all of them.
- The place filter passes an offer when one of its cities matches one the user accepts.
- A second source adds the cities it names, never removes one. The dedup key uses only the first city, so an alert naming one city and the full text naming two stay one offer.
- After renaming a field the client reads, say that an open tab must be reloaded (Cmd+Maj+R): a tab still running the old client shows the field as empty, which looks like lost data.
- When a field reads from free text, ask whether the text can state it more than once before making it a single value.

## Prevention

`test_objectives.py` checks that a two-city offer passes on either city, `test_offers.py` that a second source adds its cities, and the `extract_offer` suite has a two-city case (`ext-23`). The extraction prompt v3 measured 108/108 fields and 21/21 offer counts on 2026-11-10, against 103/103 fields for v2 on fewer cases.

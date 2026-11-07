---
date: 2026-11-07
status: active
applies_when: adding a configuration file or setting the user has to fill in, such as a key file
---

# Ship an example with each configuration file the user fills in

## What happened

The eval harness reads its own key file, but no example file came with it. The user found nothing to copy and had to ask where the key goes.

## What to do instead

In the same change that adds a configuration file the user fills in, add its `.example` file: every setting, its default, and a comment on what it does. Mention it where the command that needs it is documented.

## Prevention

A test checks that the eval key file's example lists exactly the harness's settings, with their defaults (`tests/test_evals.py`). For other configuration files, instruction only.

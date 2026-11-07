"""Application events: what happened, as a name and a few fields.

Fields are ids, counts, categories and short reasons, never a mail, a CV or a prompt:
those live in `llm_calls`, which the event points to with `llm_call_id`. An event about
an account carries its `user_id`, so that it is shown to that account only.
"""

import logging


def event(log: logging.Logger, name: str, level: int = logging.INFO, **fields: object) -> None:
    log.log(level, name, extra={"event": name, "fields": fields})

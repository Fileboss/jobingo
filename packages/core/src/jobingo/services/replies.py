"""A reply drafted by the model, for the user to edit. Nothing here sends: the edited
text goes to the approval queue, which refuses any gap left in it."""

import logging

from jobingo.db import Conn
from jobingo.domain.reply import INTENT_LABELS, ReplyDraft, ReplyRequest, reply_warnings
from jobingo.domain.style import StyleGuide
from jobingo.llm.client import LLMClient
from jobingo.llm.journal import Budget, run_task
from jobingo.llm.tasks.draft_reply import DRAFT_REPLY_TASK, DraftReplyInput
from jobingo.logs import event
from jobingo.services.applications import get_application
from jobingo.services.identity import redaction_values

log = logging.getLogger(__name__)

# What of the received message reaches the model: a long quoted thread adds cost only.
_MAX_BODY_CHARS = 8_000


def draft_reply(
    conn: Conn,
    client: LLMClient,
    budget: Budget,
    user_id: int,
    message_id: int,
    request: ReplyRequest,
    style: StyleGuide | None = None,
) -> ReplyDraft | None:
    """None: no such message. Raises what `run_task` raises. The candidate's name and
    contact details are redacted from everything sent; the signature and the sender's
    name are put in by code, at sending."""
    message = conn.execute(
        "SELECT from_addr, subject, body_text, application_id FROM messages"
        " WHERE user_id = %s AND id = %s AND kind = 'message'",
        (user_id, message_id),
    ).fetchone()
    if message is None:
        return None
    application = (
        get_application(conn, user_id, message["application_id"])
        if message["application_id"]
        else None
    )
    style = style or StyleGuide()
    output, call_id = run_task(
        conn,
        client,
        budget,
        user_id,
        DRAFT_REPLY_TASK,
        DraftReplyInput(
            from_addr=message["from_addr"],
            subject=message["subject"],
            body_text=message["body_text"][:_MAX_BODY_CHARS],
            company_name=application.company_name if application else "",
            application_title=application.title if application else "",
            intent=request.intent,
            intent_label=INTENT_LABELS[request.intent],
            instruction=request.instruction,
            style_register=style.tone_register,
            style_examples=style.examples,
            style_forbidden=style.forbidden,
        ),
        redaction_values=redaction_values(conn, user_id),
    )
    sources = f"{message['subject']}\n{message['body_text']}\n{request.instruction}"
    warnings = reply_warnings(output.body, style, sources)
    event(
        log,
        "reply.proposed",
        user_id=user_id,
        llm_call_id=call_id,
        message_id=message_id,
        application_id=message["application_id"],
        intent=request.intent,
        with_instruction=bool(request.instruction.strip()),
        words=len(output.body.split()),
        # The model's notes say what it would not do: an attack shows there first.
        model_notes=bool(output.notes.strip()),
        warnings=len(warnings),
    )
    return ReplyDraft(
        subject=output.subject.strip(),
        body=output.body.strip(),
        notes=output.notes.strip(),
        warnings=warnings,
        llm_call_id=call_id,
    )

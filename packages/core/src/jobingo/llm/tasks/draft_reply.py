from pydantic import BaseModel

from jobingo.llm.client import Task, UntrustedText


class DraftReplyInput(BaseModel):
    # The template escapes the received message itself, with the `xml` filter.
    from_addr: str
    subject: str
    body_text: str
    company_name: UntrustedText = ""
    application_title: UntrustedText = ""
    intent: str
    intent_label: str
    instruction: str = ""
    style_register: str = ""
    style_examples: list[str] = []
    style_forbidden: list[str] = []
    style_max_words: int | None = None


class DraftReplyOutput(BaseModel):
    subject: str
    body: str
    # For the user only: what to check, what the message asked that was not done.
    notes: str = ""


DRAFT_REPLY_TASK: Task[DraftReplyInput, DraftReplyOutput] = Task(
    name="draft_reply",
    tier="writing",
    input_model=DraftReplyInput,
    output_model=DraftReplyOutput,
    # v4: a missing fact becomes a canonical `[À COMPLÉTER : …]` marker.
    user_template="draft_reply.v4.md",
    system_template="draft_reply.v4.system.md",
    prompt_version=4,
    max_tokens=4096,
)

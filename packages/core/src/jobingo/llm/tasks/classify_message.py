from typing import Literal

from pydantic import BaseModel

from jobingo.llm.client import Task, UntrustedText


class ClassifyMessageInput(BaseModel):
    from_addr: UntrustedText
    subject: UntrustedText
    body_text: UntrustedText


class ClassifyMessageOutput(BaseModel):
    category: Literal["offer", "rejection", "interview", "recruiter_other", "other"]
    company_name: str = ""
    # An ISO date, only when the message states one; code parses it and drops the rest.
    interview_date: str | None = None
    summary: str = ""


CLASSIFY_MESSAGE_TASK: Task[ClassifyMessageInput, ClassifyMessageOutput] = Task(
    name="classify_message",
    tier="fast",
    input_model=ClassifyMessageInput,
    output_model=ClassifyMessageOutput,
    user_template="classify_message.v2.md",
    system_template="classify_message.v2.system.md",
    prompt_version=2,
    max_tokens=1024,
)

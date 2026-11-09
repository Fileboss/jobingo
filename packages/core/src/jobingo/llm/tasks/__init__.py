"""One module per bounded task: its typed input, its validated output, its prompts."""

from typing import Any

from jobingo.llm.client import Task
from jobingo.llm.tasks.classify_message import CLASSIFY_MESSAGE_TASK
from jobingo.llm.tasks.draft_letter import DRAFT_LETTER_TASK
from jobingo.llm.tasks.draft_reply import DRAFT_REPLY_TASK
from jobingo.llm.tasks.extract_offer import EXTRACT_OFFER_TASK
from jobingo.llm.tasks.score_offer import SCORE_OFFER_TASK
from jobingo.llm.tasks.select_cv_content import SELECT_CV_CONTENT_TASK

# Every task the app ships, with the prompt version it ships.
TASKS: dict[str, Task[Any, Any]] = {
    task.name: task
    for task in (
        CLASSIFY_MESSAGE_TASK,
        DRAFT_LETTER_TASK,
        DRAFT_REPLY_TASK,
        EXTRACT_OFFER_TASK,
        SCORE_OFFER_TASK,
        SELECT_CV_CONTENT_TASK,
    )
}

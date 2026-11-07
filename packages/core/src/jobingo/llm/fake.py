from collections import defaultdict
from typing import Any

from pydantic import BaseModel

from jobingo.llm.client import LLMCallError, LLMResult, LLMValidationError, Prompt, Task, Usage


class FakeLLMClient:
    """Replays queued answers instead of calling Anthropic: tests never call a real model.

    Answers are queued per task and consumed in order. Queuing an `LLMCallError`
    simulates a call that failed, with whatever usage it carries.
    """

    def __init__(self, model: str = "claude-haiku-5-5", usage: Usage | None = None) -> None:
        self.model = model
        self.usage = usage or Usage(input_tokens=1000, output_tokens=200, attempts=1)
        self.prompts: list[tuple[str, Prompt]] = []
        self._queues: dict[str, list[BaseModel | LLMCallError]] = defaultdict(list)

    def queue(self, task_name: str, answer: BaseModel | LLMCallError) -> None:
        self._queues[task_name].append(answer)

    def run[OutT: BaseModel](self, task: Task[Any, OutT], prompt: Prompt) -> LLMResult[OutT]:
        self.prompts.append((task.name, prompt))
        request: dict[str, Any] = {
            "model": self.model,
            "system": prompt.system,
            "user": prompt.user,
        }
        queue = self._queues[task.name]
        if not queue:
            raise LLMValidationError(
                f"no fake answer queued for task {task.name!r}",
                model=self.model,
                usage=Usage(),
                request=request,
            )
        answer = queue.pop(0)
        if isinstance(answer, LLMCallError):
            raise answer
        output = task.output_model.model_validate(answer.model_dump())
        return LLMResult(
            output=output,
            model=self.model,
            usage=self.usage,
            request=request,
            response=answer.model_dump(mode="json"),
        )

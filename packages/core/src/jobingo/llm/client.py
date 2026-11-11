"""What every model call has in common: a bounded task, the client that runs it, and
what a call returns or raises. A task has a typed input, a validated output, and no tools.
"""

from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Protocol

from jinja2 import Environment
from pydantic import AfterValidator, BaseModel

from jobingo.llm.prompts import PROMPTS, escape_tags

type Tier = Literal["fast", "writing"]

# A task input field holding text the user did not write: a mail, a pasted offer.
UntrustedText = Annotated[str, AfterValidator(escape_tags)]


@dataclass(frozen=True)
class Task[InT: BaseModel, OutT: BaseModel]:
    name: str
    tier: Tier
    input_model: type[InT]
    output_model: type[OutT]
    # Template names, rendered with `payload`. The system part is the stable one, sent
    # with a cache marker: anything that varies per call belongs in the user part.
    user_template: str
    system_template: str | None = None
    prompt_version: int = 1
    # Bounds the worst-case cost of one answer: a runaway answer fails the attempt.
    max_tokens: int = 16000
    # The schema sent to the API when it must differ from `output_model`, since strict
    # structured output forbids free-form mappings. Its answer must still validate as
    # `output_model`.
    schema_model: type[BaseModel] | None = None
    prompts: Environment = field(default=PROMPTS, compare=False, repr=False)


@dataclass(frozen=True)
class Prompt:
    """A task's prompts as rendered and redacted: exactly what the model reads."""

    user: str
    system: str | None = None


@dataclass(frozen=True)
class Usage:
    """What a call consumed, summed over its attempts: every attempt is billed."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    latency_ms: int = 0
    attempts: int = 0


@dataclass(frozen=True)
class LLMResult[OutT: BaseModel]:
    output: OutT
    model: str
    usage: Usage
    request: dict[str, Any]
    response: dict[str, Any]


class LLMCallError(Exception):
    """A call that produced no usable output. It carries what is known about the call,
    so that it is still journalled and costed: a failed call spent tokens too."""

    def __init__(
        self,
        message: str,
        *,
        model: str,
        usage: Usage,
        request: dict[str, Any],
        response: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.model = model
        self.usage = usage
        self.request = request
        self.response = response


class LLMValidationError(LLMCallError):
    """The answer was truncated, refused or invalid, again after one retry."""


class LLMUnavailable(LLMCallError):
    """The API could not be reached or refused the request, after the SDK's own
    retries. The user gets its cause, never a 500."""

    # Why, in French, for the user: a refused key is not an outage.
    reason: str = "L'API Anthropic ne répond pas. Réessayez dans un instant."


class LLMClient(Protocol):
    def run[OutT: BaseModel](self, task: Task[Any, OutT], prompt: Prompt) -> LLMResult[OutT]: ...

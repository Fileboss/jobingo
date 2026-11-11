import logging
import time
from dataclasses import dataclass, replace
from typing import Any, Literal, cast

import anthropic
from anthropic.types import Message
from pydantic import BaseModel, ValidationError

from jobingo.llm.client import (
    LLMResult,
    LLMUnavailable,
    LLMValidationError,
    Prompt,
    Task,
    Tier,
    Usage,
)
from jobingo.llm.pricing import check_priced
from jobingo.logs import event

log = logging.getLogger(__name__)

type Thinking = Literal["off", "adaptive"]
type Effort = Literal["low", "medium", "high", "xhigh", "max"]

# Thinking cannot be turned off on these: `disabled` is a 400 at every effort.
_ALWAYS_THINKING = {"claude-opus-5-5"}
# Sonnet 5.5 rejects `disabled`. Its lowest setting is `between_tools`, which, in a
# request with no tools, means no thinking at all.
_OFF_IS_BETWEEN_TOOLS = {"claude-sonnet-5-5"}


@dataclass(frozen=True)
class TierSettings:
    model: str
    thinking: Thinking
    effort: Effort


def output_schema(task: Task[Any, Any]) -> dict[str, Any]:
    """The JSON schema the API constrains the answer to. `transform_schema` makes it
    strict and drops the keywords the API does not support, such as `ge`: Pydantic still
    enforces those when the answer is validated."""
    return anthropic.transform_schema(task.schema_model or task.output_model)


def _check_tier(tier: TierSettings) -> None:
    check_priced(tier.model)
    if tier.thinking == "off":
        if tier.model in _ALWAYS_THINKING:
            raise ValueError(f"{tier.model} cannot run with thinking off")
        if tier.effort in ("xhigh", "max"):
            raise ValueError(f"thinking off accepts effort low, medium or high, not {tier.effort}")


def _reason(error: anthropic.APIError, model: str) -> str:
    """What the user can do about it, in French: most refusals are settings to fix."""
    if isinstance(error, anthropic.AuthenticationError):
        return (
            "La clé Anthropic est refusée : vérifiez ANTHROPIC_API_KEY dans la configuration, "
            "puis relancez l'API."
        )
    if isinstance(error, anthropic.PermissionDeniedError):
        return "La clé Anthropic n'a pas accès à cette API ou à ce modèle."
    if isinstance(error, anthropic.NotFoundError):
        return (
            f"Le modèle {model} est inconnu de l'API : vérifiez LLM_MODEL_FAST et "
            "LLM_MODEL_WRITING dans la configuration."
        )
    if isinstance(error, anthropic.BadRequestError) and "credit balance" in str(error).lower():
        return "Le crédit du compte Anthropic est épuisé : rechargez-le dans la console Anthropic."
    if isinstance(error, anthropic.RateLimitError):
        return "L'API Anthropic limite le débit : réessayez dans un instant."
    if isinstance(error, anthropic.BadRequestError):
        return "L'API Anthropic a refusé la requête : le détail est dans le journal des appels."
    return LLMUnavailable.reason


class AnthropicLLMClient:
    """The real `LLMClient`. It constrains the answer with structured output, validates
    it against the task's model, and retries once on a truncated, refused or invalid
    answer.

    `messages.create` rather than `messages.parse`: `parse` validates inside the HTTP
    call, so an invalid answer would raise without its token counts, and the journal
    costs failed calls too.
    """

    def __init__(self, sdk: anthropic.Anthropic, tiers: dict[Tier, TierSettings]) -> None:
        for tier in tiers.values():
            _check_tier(tier)
        self._sdk = sdk
        self._tiers = tiers

    def params(self, task: Task[Any, Any], prompt: Prompt) -> dict[str, Any]:
        """The request of a first attempt, exactly as `run` sends it."""
        tier = self._tiers[task.tier]
        params: dict[str, Any] = {
            "model": tier.model,
            "max_tokens": task.max_tokens,
            "output_config": {
                "effort": tier.effort,
                "format": {"type": "json_schema", "schema": output_schema(task)},
            },
            "messages": [{"role": "user", "content": prompt.user}],
        }
        if tier.thinking == "adaptive":
            params["thinking"] = {"type": "adaptive"}
        elif tier.model in _OFF_IS_BETWEEN_TOOLS:
            params["thinking"] = {"type": "between_tools"}
        else:
            params["thinking"] = {"type": "disabled"}
        if prompt.system is not None:
            # Below the model's minimum cacheable length the marker is ignored, at no
            # cost. Above it, a repeat within 5 minutes reads the prefix at a fraction.
            params["system"] = [
                {"type": "text", "text": prompt.system, "cache_control": {"type": "ephemeral"}}
            ]
        return params

    def run[OutT: BaseModel](self, task: Task[Any, OutT], prompt: Prompt) -> LLMResult[OutT]:
        params = self.params(task, prompt)
        model: str = params["model"]
        usage = Usage()
        response: dict[str, Any] | None = None
        last_error: str | None = None

        for attempt in (1, 2):
            if last_error is not None:
                event(log, "llm.retry", logging.WARNING, task=task.name, reason=last_error[:300])
                message = (
                    f"{prompt.user}\n\nL'appel précédent a échoué la validation : {last_error}. "
                    "Corrige et renvoie un objet valide."
                )
                params["messages"] = [{"role": "user", "content": message}]
            started = time.monotonic()
            try:
                # A dict of parameters defeats the overloads: without `stream`, it is a Message.
                answer = cast(Message, self._sdk.messages.create(**params))
            except anthropic.APIError as exc:
                elapsed = int((time.monotonic() - started) * 1000)
                unavailable = LLMUnavailable(
                    f"Anthropic API unavailable ({task.name}): {exc}",
                    model=model,
                    usage=replace(usage, attempts=attempt, latency_ms=usage.latency_ms + elapsed),
                    request=params,
                    response=response,
                )
                unavailable.reason = _reason(exc, model)
                raise unavailable from exc
            elapsed = int((time.monotonic() - started) * 1000)
            counted = answer.usage
            usage = Usage(
                input_tokens=usage.input_tokens + counted.input_tokens,
                output_tokens=usage.output_tokens + counted.output_tokens,
                cache_read_tokens=usage.cache_read_tokens + (counted.cache_read_input_tokens or 0),
                cache_write_tokens=usage.cache_write_tokens
                + (counted.cache_creation_input_tokens or 0),
                latency_ms=usage.latency_ms + elapsed,
                attempts=attempt,
            )
            answered = answer.to_dict()
            response = answered

            if answer.stop_reason == "max_tokens":
                last_error = f"response truncated at max_tokens ({task.max_tokens})"
                continue
            if answer.stop_reason == "refusal":
                last_error = "the model declined to answer"
                continue
            text = next((b.text for b in answer.content if b.type == "text"), None)
            if text is None:
                last_error = "no text block in the response"
                continue
            try:
                output = task.output_model.model_validate_json(text)
            except ValidationError as exc:
                last_error = str(exc)
                continue
            return LLMResult(
                output=output, model=model, usage=usage, request=params, response=answered
            )

        raise LLMValidationError(
            f"validation failed for task {task.name!r}: {last_error}",
            model=model,
            usage=usage,
            request=params,
            response=response,
        )

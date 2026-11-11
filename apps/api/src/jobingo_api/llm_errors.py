"""What a route that calls the model answers when the call cannot happen or fails: a
message the user can read, never a 500. A failed call is journalled all the same."""

from typing import Any

from fastapi.responses import JSONResponse

from jobingo.llm.client import LLMUnavailable, LLMValidationError
from jobingo.llm.journal import LLMBudgetExceeded
from jobingo_api.schemas import Refused

LLM_RESPONSES: dict[int | str, dict[str, Any]] = {
    429: {"model": Refused, "description": "A spending cap is reached"},
    502: {"model": Refused, "description": "The model's answer was unusable"},
    503: {"model": Refused, "description": "No API key, or the API is unavailable"},
}


def refused(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content=Refused(message=message).model_dump())


def not_configured() -> JSONResponse:
    return refused(
        503, "L'IA n'est pas configurée : renseignez ANTHROPIC_API_KEY, puis relancez l'API."
    )


def llm_refusal(error: Exception) -> JSONResponse | None:
    """The answer for a failure of the model call, None for any other error."""
    if isinstance(error, LLMBudgetExceeded):
        return refused(429, f"Aucun appel : {error}. Le plafond se règle dans la configuration.")
    if isinstance(error, LLMUnavailable):
        return refused(503, error.reason)
    if isinstance(error, LLMValidationError):
        return refused(
            502, "La réponse du modèle était inutilisable, même après une relance. Réessayez."
        )
    return None

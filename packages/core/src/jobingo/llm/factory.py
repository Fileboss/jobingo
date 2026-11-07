import anthropic

from jobingo.config import Settings
from jobingo.llm.anthropic_client import AnthropicLLMClient, TierSettings
from jobingo.llm.client import LLMClient
from jobingo.llm.journal import Budget


def create_llm_client(settings: Settings) -> LLMClient | None:
    """None without an API key: the app still runs, and says the AI is not configured."""
    key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else ""
    if not key:
        return None
    sdk = anthropic.Anthropic(api_key=key)
    return AnthropicLLMClient(
        sdk,
        {
            "fast": TierSettings(
                settings.llm_model_fast, settings.llm_fast_thinking, settings.llm_fast_effort
            ),
            "writing": TierSettings(
                settings.llm_model_writing,
                settings.llm_writing_thinking,
                settings.llm_writing_effort,
            ),
        },
    )


def budget(settings: Settings) -> Budget:
    return Budget(settings.llm_daily_budget_usd, settings.llm_monthly_budget_usd)

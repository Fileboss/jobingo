"""What a call costs, from its measured token counts and the published prices.

Prices are Anthropic's first-party rates in USD per million tokens, from Anthropic's
model documentation as of 2026-10-06. Check the pricing page before relying on or
changing one: every cost on the observability page and every budget cap derives from
this table.
"""

from dataclasses import dataclass
from decimal import Decimal

from jobingo.llm.client import Usage

# A 5-minute cache write costs 1.25 times the input rate, on every model.
_CACHE_WRITE = Decimal("1.25")
_MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class Rates:
    input: Decimal
    output: Decimal
    cache_read: Decimal


@dataclass(frozen=True)
class Price:
    rates: Rates
    # Haiku 5.5 bills a whole call at higher rates when its prompt is longer than this.
    long_prompt: tuple[int, Rates] | None = None


def _rates(input: str, output: str, cache_read: str) -> Rates:
    return Rates(Decimal(input), Decimal(output), Decimal(cache_read))


PRICES: dict[str, Price] = {
    "claude-haiku-5-5": Price(
        _rates("0.10", "0.50", "0.01"), long_prompt=(100_000, _rates("0.50", "2.50", "0.05"))
    ),
    "claude-sonnet-5-5": Price(_rates("2", "10", "0.20")),
    "claude-opus-5-5": Price(_rates("4", "20", "0.20")),
}


class UnknownModelError(ValueError):
    pass


def check_priced(model: str) -> None:
    """A model without a price would make every cost and every cap wrong."""
    if model not in PRICES:
        raise UnknownModelError(f"no price for model {model!r}, add it to llm/pricing.py")


def cost_usd(model: str, usage: Usage) -> Decimal:
    """`input_tokens` excludes cached tokens: the API reports them apart, at their rate."""
    check_priced(model)
    price = PRICES[model]
    rates = price.rates
    # The threshold applies to each request: a retried call sent its prompt twice.
    prompt_tokens = usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens
    per_request = prompt_tokens / max(usage.attempts, 1)
    if price.long_prompt is not None and per_request > price.long_prompt[0]:
        rates = price.long_prompt[1]
    total = (
        usage.input_tokens * rates.input
        + usage.cache_write_tokens * rates.input * _CACHE_WRITE
        + usage.cache_read_tokens * rates.cache_read
        + usage.output_tokens * rates.output
    )
    return (total / _MILLION).quantize(Decimal("0.000001"))

"""Estimate run cost from token usage using a (dated, advisory) price table."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agon.cost.prices import DEFAULT_PRICES, PRICES_AS_OF, price_for
from agon.sut.contract import TokenUsage

_PER_MTOK = 1_000_000


class CostEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    input_usd: float = 0.0
    output_usd: float = 0.0
    total_usd: float = 0.0
    priced: bool = False
    note: str | None = None


class CostSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: str = PRICES_AS_OF
    total_usd: float = 0.0
    priced: bool = True  # True iff every model that had usage was priced
    usage: TokenUsage = Field(default_factory=TokenUsage)
    by_model: list[CostEstimate] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def estimate_cost(
    model: str,
    usage: TokenUsage,
    prices: dict[str, tuple[float, float]] = DEFAULT_PRICES,
) -> CostEstimate:
    """Cost for one model's usage. Zero usage is free (and unnoted); unknown non-zero usage is
    unpriced with a note."""
    # Zero usage is always free -- avoids spurious "no price" notes on offline mockllm runs.
    if usage.total == 0:
        return CostEstimate(model=model, priced=True)
    rates = price_for(model, prices)
    if rates is None:
        return CostEstimate(model=model, priced=False, note=f"no price for {model}")
    in_rate, out_rate = rates
    input_usd = usage.input / _PER_MTOK * in_rate
    output_usd = usage.output / _PER_MTOK * out_rate
    return CostEstimate(
        model=model,
        input_usd=input_usd,
        output_usd=output_usd,
        total_usd=input_usd + output_usd,
        priced=True,
    )


def summarize_cost(
    usage_by_model: dict[str, TokenUsage],
    prices: dict[str, tuple[float, float]] = DEFAULT_PRICES,
) -> CostSummary:
    """Aggregate per-model usage into a run-level cost summary."""
    by_model: list[CostEstimate] = []
    total_usd = 0.0
    agg = TokenUsage()
    notes: list[str] = []
    all_priced = True
    for model, usage in sorted(usage_by_model.items()):
        est = estimate_cost(model, usage, prices)
        by_model.append(est)
        total_usd += est.total_usd
        agg = TokenUsage(
            input=agg.input + usage.input,
            output=agg.output + usage.output,
            total=agg.total + usage.total,
        )
        if not est.priced:
            all_priced = False
            if est.note:
                notes.append(est.note)
    return CostSummary(
        total_usd=total_usd,
        priced=all_priced,
        usage=agg,
        by_model=by_model,
        notes=notes,
    )

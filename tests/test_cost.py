"""Phase 3 M5 -- cost estimation from token usage (dated, advisory price table)."""

from agon.cost import CostSummary, estimate_cost, summarize_cost
from agon.sut import TokenUsage

# A controlled table so cost math is independent of the shipped DEFAULT_PRICES values.
PRICES = {"test-model": (2.0, 6.0)}  # USD per 1M tokens (input, output)


def test_estimate_known_model():
    usage = TokenUsage(input=1_000_000, output=500_000, total=1_500_000)
    est = estimate_cost("test-model", usage, PRICES)
    assert est.priced is True
    assert est.input_usd == 2.0
    assert est.output_usd == 3.0
    assert est.total_usd == 5.0


def test_estimate_strips_provider_prefix():
    usage = TokenUsage(input=2_000_000, output=0, total=2_000_000)
    est = estimate_cost("openai/test-model", usage, PRICES)
    assert est.priced is True
    assert est.total_usd == 4.0


def test_estimate_zero_usage_is_free_and_unnoted():
    est = estimate_cost("anything-unknown", TokenUsage(), PRICES)
    assert est.priced is True
    assert est.total_usd == 0.0
    assert est.note is None


def test_estimate_unknown_model_with_usage_is_unpriced_with_note():
    est = estimate_cost("mystery-model", TokenUsage(input=1000, output=10, total=1010), PRICES)
    assert est.priced is False
    assert est.total_usd == 0.0
    assert est.note is not None and "mystery-model" in est.note


def test_summarize_aggregates_and_flags_partial():
    usage_by_model = {
        "test-model": TokenUsage(input=1_000_000, output=0, total=1_000_000),
        "mystery-model": TokenUsage(input=1000, output=10, total=1010),
    }
    summary = summarize_cost(usage_by_model, PRICES)
    assert isinstance(summary, CostSummary)
    assert summary.total_usd == 2.0  # only the priced model contributes
    assert summary.usage.total == 1_001_010
    assert summary.priced is False  # one model was unpriced
    assert any("mystery-model" in n for n in summary.notes)
    assert summary.as_of  # dated


def test_summarize_empty_usage_is_free_and_priced():
    summary = summarize_cost({}, PRICES)
    assert summary.total_usd == 0.0
    assert summary.usage.total == 0
    assert summary.priced is True


def test_estimate_free_provider_is_zero_and_priced():
    # mockllm (and other mock providers) are free by construction, even with synthetic tokens.
    est = estimate_cost("mockllm/model", TokenUsage(input=1, output=33, total=34), PRICES)
    assert est.priced is True
    assert est.total_usd == 0.0
    assert est.note is None

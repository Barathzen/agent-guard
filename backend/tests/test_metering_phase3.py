from decimal import Decimal

import pytest

from backend.app.domain.metering import (
    calculate_actual_cost,
    calculate_estimated_cost,
    calculate_token_cost,
)
from backend.app.db.models import ModelPricing


def pricing() -> ModelPricing:
    return ModelPricing(
        id="mock-v1",
        provider="mock",
        model_name="mock-gpt-4o",
        input_price_per_m=Decimal("1.25"),
        output_price_per_m=Decimal("5.50"),
        currency="USD",
        pricing_version="v1",
    )


def test_token_cost_rounds_at_ledger_precision():
    assert calculate_token_cost(
        1, 1, Decimal("1.234567"), Decimal("2.345678")
    ) == Decimal("0.000004")


def test_zero_and_single_category_usage():
    assert calculate_token_cost(0, 0, Decimal("10"), Decimal("20")) == Decimal("0.000000")
    assert calculate_token_cost(1000, 0, Decimal("1"), Decimal("2")) == Decimal("0.001000")
    assert calculate_token_cost(0, 1000, Decimal("1"), Decimal("2")) == Decimal("0.002000")


def test_estimate_uses_maximum_output_and_actual_uses_provider_usage():
    model_pricing = pricing()
    assert calculate_estimated_cost(100, 500, model_pricing) == Decimal("0.002875")
    assert calculate_actual_cost(100, 42, model_pricing) == Decimal("0.000356")


def test_negative_token_counts_are_rejected():
    with pytest.raises(ValueError, match="cannot be negative"):
        calculate_token_cost(-1, 0, Decimal("1"), Decimal("1"))

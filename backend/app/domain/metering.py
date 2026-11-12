from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import ModelPricing, UsageRecord

MILLION = Decimal("1000000")
LEDGER_QUANTUM = Decimal("0.000001")


class PricingNotFoundError(LookupError):
    pass


def calculate_token_cost(
    input_tokens: int,
    output_tokens: int,
    input_price_per_m: Decimal,
    output_price_per_m: Decimal,
) -> Decimal:
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("Token counts cannot be negative")
    raw_cost = (
        Decimal(input_tokens) * input_price_per_m
        + Decimal(output_tokens) * output_price_per_m
    ) / MILLION
    return raw_cost.quantize(LEDGER_QUANTUM)


async def resolve_pricing(
    db: AsyncSession,
    provider: str,
    model_name: str,
    at: Optional[datetime] = None,
) -> ModelPricing:
    effective_at = at or datetime.now(timezone.utc)
    result = await db.execute(
        select(ModelPricing)
        .where(
            ModelPricing.provider == provider,
            ModelPricing.model_name == model_name,
            ModelPricing.effective_from <= effective_at,
            (ModelPricing.effective_to.is_(None) | (ModelPricing.effective_to > effective_at)),
        )
        .order_by(ModelPricing.effective_from.desc())
        .limit(1)
    )
    pricing = result.scalar_one_or_none()
    if pricing is None:
        raise PricingNotFoundError(f"No active pricing found for {provider}/{model_name}")
    return pricing


def calculate_estimated_cost(
    input_tokens: int,
    max_output_tokens: int,
    pricing: ModelPricing,
) -> Decimal:
    return calculate_token_cost(
        input_tokens,
        max_output_tokens,
        pricing.input_price_per_m,
        pricing.output_price_per_m,
    )


def calculate_actual_cost(
    input_tokens: int,
    output_tokens: int,
    pricing: ModelPricing,
) -> Decimal:
    return calculate_token_cost(
        input_tokens,
        output_tokens,
        pricing.input_price_per_m,
        pricing.output_price_per_m,
    )


async def persist_usage(
    db: AsyncSession,
    *,
    request_id: str,
    team_id: str,
    agent_id: str,
    session_id: str,
    provider: str,
    model_name: str,
    pricing: ModelPricing,
    estimated_input_tokens: int,
    estimated_output_tokens: int,
    actual_input_tokens: int,
    actual_output_tokens: int,
    estimated_cost: Decimal,
    actual_cost: Decimal,
) -> UsageRecord:
    record = UsageRecord(
        id=f"usage-{request_id}",
        request_id=request_id,
        team_id=team_id,
        agent_id=agent_id,
        session_id=session_id,
        provider=provider,
        model_name=model_name,
        pricing_version=pricing.pricing_version,
        currency=pricing.currency,
        estimated_input_tokens=estimated_input_tokens,
        estimated_output_tokens=estimated_output_tokens,
        actual_input_tokens=actual_input_tokens,
        actual_output_tokens=actual_output_tokens,
        estimated_cost=estimated_cost,
        actual_cost=actual_cost,
    )
    db.add(record)
    await db.commit()
    return record

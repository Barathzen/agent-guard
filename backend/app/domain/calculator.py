from decimal import Decimal, ROUND_HALF_UP

def calculate_token_cost(
    input_tokens: int,
    output_tokens: int,
    input_price_per_m: Decimal,
    output_price_per_m: Decimal
) -> Decimal:
    raw_cost = (
        (Decimal(input_tokens) * input_price_per_m) +
        (Decimal(output_tokens) * output_price_per_m)
    ) / Decimal("1000000")
    return raw_cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
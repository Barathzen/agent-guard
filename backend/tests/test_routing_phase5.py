from decimal import Decimal

from backend.app.domain.routing import RouteCandidate, select_candidates, substitution_reason


def candidate(name: str, input_price: str, output_price: str, capabilities=()):
    return RouteCandidate(
        model_name=name,
        input_price_per_m=Decimal(input_price),
        output_price_per_m=Decimal(output_price),
        capabilities=frozenset(capabilities),
    )


def test_fallbacks_are_filtered_to_allowed_compatible_cheaper_models():
    models = [
        candidate("preferred", "10", "20", ["vision"]),
        candidate("cheap-compatible", "1", "2", ["vision"]),
        candidate("cheap-incompatible", "1", "2"),
        candidate("expensive", "11", "22", ["vision"]),
    ]

    selected = select_candidates(
        "preferred",
        models,
        allowed_models=["preferred", "cheap-compatible", "cheap-incompatible", "expensive"],
        fallback_models=["cheap-incompatible", "expensive", "cheap-compatible"],
        required_capabilities=["vision"],
    )

    assert [model.model_name for model in selected] == ["preferred", "cheap-compatible"]


def test_unavailable_preferred_model_can_use_compatible_fallback():
    models = [
        candidate("preferred", "10", "20"),
        RouteCandidate(
            model_name="fallback",
            input_price_per_m=Decimal("1"),
            output_price_per_m=Decimal("2"),
            available=False,
        ),
        candidate("available-fallback", "1", "2"),
    ]
    selected = select_candidates(
        "preferred",
        models,
        fallback_models=["fallback", "available-fallback"],
    )

    assert [model.model_name for model in selected] == ["preferred", "available-fallback"]


def test_substitution_reason_is_traceable():
    assert substitution_reason("preferred", "cheap") is not None
    assert substitution_reason("preferred", "preferred") is None

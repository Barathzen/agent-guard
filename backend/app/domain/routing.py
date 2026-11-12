from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable


@dataclass(frozen=True)
class RouteCandidate:
    model_name: str
    input_price_per_m: Decimal
    output_price_per_m: Decimal
    available: bool = True
    capabilities: frozenset[str] = frozenset()
    max_context_tokens: int = 128000

    @property
    def output_price(self) -> Decimal:
        return self.output_price_per_m


def select_candidates(
    requested_model: str,
    candidates: Iterable[RouteCandidate],
    *,
    allowed_models: Iterable[str] = (),
    fallback_models: Iterable[str] = (),
    required_capabilities: Iterable[str] = (),
    input_tokens: int = 0,
    max_output_tokens: int = 0,
) -> list[RouteCandidate]:
    by_name = {candidate.model_name: candidate for candidate in candidates}
    allowed = set(allowed_models)
    required = set(required_capabilities)
    ordered_names = [requested_model, *fallback_models]
    result: list[RouteCandidate] = []
    seen: set[str] = set()
    for name in ordered_names:
        if name in seen:
            continue
        seen.add(name)
        candidate = by_name.get(name)
        if candidate is None or not candidate.available:
            continue
        if allowed and name not in allowed and name != requested_model:
            continue
        if not required.issubset(candidate.capabilities):
            continue
        if input_tokens + max_output_tokens > candidate.max_context_tokens:
            continue
        result.append(candidate)
    if not result:
        return []
    preferred = result[0]
    cheaper = [
        candidate for candidate in result[1:]
        if candidate.input_price_per_m <= preferred.input_price_per_m
        and candidate.output_price_per_m <= preferred.output_price_per_m
        and (
            candidate.input_price_per_m < preferred.input_price_per_m
            or candidate.output_price_per_m < preferred.output_price_per_m
        )
    ]
    return [preferred, *cheaper]


def substitution_reason(requested_model: str, selected_model: str) -> str | None:
    if requested_model == selected_model:
        return None
    return f"requested model unavailable or over budget; selected compatible fallback {selected_model}"

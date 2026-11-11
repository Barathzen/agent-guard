import asyncio
import time
from typing import List, Dict, Optional
from backend.app.providers.base import AbstractLLMProvider, ProviderResponse, TokenUsage

class MockLLMProvider(AbstractLLMProvider):
    def __init__(self, base_latency_ms: float = 50.0):
        self.base_latency_ms = base_latency_ms

    def estimate_input_tokens(self, messages: List[Dict[str, str]]) -> int:
        # Heuristic: 4 chars ~= 1 token + 10 overhead tokens
        raw_text = "".join(m.get("content", "") for m in messages)
        return max(len(raw_text) // 4, 1) + 10

    async def generate(
        self,
        request_id: str,
        model: str,
        messages: List[Dict[str, str]],
        max_output_tokens: int,
        simulate_error: Optional[str] = None
    ) -> ProviderResponse:
        start_time = time.perf_counter()

        # Simulate provider latency
        await asyncio.sleep(self.base_latency_ms / 1000.0)

        # Support failure simulation
        if simulate_error == "timeout":
            raise asyncio.TimeoutError("Upstream provider timed out")
        elif simulate_error == "provider_error":
            raise RuntimeError("Upstream provider returned 500 internal server error")

        input_tokens = self.estimate_input_tokens(messages)
        output_tokens = min(max_output_tokens, 42)

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return ProviderResponse(
            request_id=request_id,
            content=f"[Mock Provider Output for {model}]: Intercepted successfully.",
            model=model,
            usage=TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens),
            latency_ms=round(elapsed_ms, 2)
        )
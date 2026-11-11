from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from pydantic import BaseModel, Field

class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int

class ProviderResponse(BaseModel):
    request_id: str
    content: str
    model: str
    usage: TokenUsage
    latency_ms: float

class AbstractLLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        request_id: str,
        model: str,
        messages: List[Dict[str, str]],
        max_output_tokens: int,
        simulate_error: Optional[str] = None
    ) -> ProviderResponse:
        pass

    @abstractmethod
    def estimate_input_tokens(self, messages: List[Dict[str, str]]) -> int:
        pass
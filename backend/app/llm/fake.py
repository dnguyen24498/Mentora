from collections.abc import AsyncIterator

from app.llm.models import LLMRequest, LLMResponse, LLMTier
from app.llm.provider import LLMProvider


class FakeLLMProvider(LLMProvider):
    """Deterministic stub for tests and local development.

    Returns an echo of the last user message; no network or API key required.
    """

    def __init__(self, name: str, tier: LLMTier) -> None:
        self.name = name
        self.tier = tier

    async def generate(self, request: LLMRequest) -> LLMResponse:
        last = request.messages[-1].content
        content = f"[{self.name}] {last}"
        return LLMResponse(
            content=content,
            tier=request.tier or self.tier,
            model=self.name,
            usage_tokens=len(content.split()),
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        response = await self.generate(request)
        for word in response.content.split():
            yield word + " "

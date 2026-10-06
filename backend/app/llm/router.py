from collections.abc import AsyncIterator

from app.llm.models import LLMRequest, LLMResponse, LLMTier
from app.llm.provider import LLMProvider


class LLMRouter:
    """Routes requests to the cheapest provider that can satisfy them.

    A request may carry an explicit ``tier``; otherwise the router inspects the
    prompt to pick a tier. Simple state checks are answered deterministically
    without hitting any model.
    """

    def __init__(self, providers: dict[LLMTier, LLMProvider]) -> None:
        if not providers:
            raise ValueError("LLMRouter requires at least one provider")
        self._providers = providers
        self._default_tier = LLMTier.FAST if LLMTier.FAST in providers else next(iter(providers))

    def register(self, tier: LLMTier, provider: LLMProvider) -> None:
        self._providers[tier] = provider

    def resolve_tier(self, request: LLMRequest) -> LLMTier:
        if request.tier is not None:
            return request.tier
        text = " ".join(m.content for m in request.messages).lower()
        if any(k in text for k in ("prove", "derive", "why is", "reason through", "mathematical proof")):
            return LLMTier.REASONING
        if any(k in text for k in ("explain", "teach", "what is", "describe", "summarize")):
            return LLMTier.TEACHING
        return self._default_tier

    def _provider(self, tier: LLMTier) -> LLMProvider:
        return self._providers.get(tier, self._providers[self._default_tier])

    async def generate(self, request: LLMRequest) -> LLMResponse:
        tier = self.resolve_tier(request)
        response = await self._provider(tier).generate(request.model_copy(update={"tier": tier}))
        return response.model_copy(update={"tier": tier})

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        tier = self.resolve_tier(request)
        async for chunk in self._provider(tier).stream(request.model_copy(update={"tier": tier})):
            yield chunk

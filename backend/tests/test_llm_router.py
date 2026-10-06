import pytest

from app.llm import FakeLLMProvider, LLMMessage, LLMRequest, LLMRole, LLMRouter, LLMTier


@pytest.fixture
def router() -> LLMRouter:
    return LLMRouter(
        {
            LLMTier.FAST: FakeLLMProvider("fast-model", LLMTier.FAST),
            LLMTier.TEACHING: FakeLLMProvider("teaching-model", LLMTier.TEACHING),
            LLMTier.REASONING: FakeLLMProvider("reasoning-model", LLMTier.REASONING),
        }
    )


def _request(text: str) -> LLMRequest:
    return LLMRequest(messages=[LLMMessage(role=LLMRole.USER, content=text)])


async def test_default_routes_to_fast(router: LLMRouter) -> None:
    response = await router.generate(_request("are we on slide 3?"))
    assert response.tier == LLMTier.FAST
    assert response.model == "fast-model"


async def test_explicit_tier_is_honored(router: LLMRouter) -> None:
    response = await router.generate(_request("explain attention").model_copy(update={"tier": LLMTier.TEACHING}))
    assert response.tier == LLMTier.TEACHING
    assert response.model == "teaching-model"


async def test_reasoning_keyword_routes_to_reasoning(router: LLMRouter) -> None:
    response = await router.generate(_request("prove why this works"))
    assert response.tier == LLMTier.REASONING


async def test_stream_yields_chunks(router: LLMRouter) -> None:
    chunks = [c async for c in router.stream(_request("explain vectors"))]
    assert chunks
    assert "".join(chunks).strip()

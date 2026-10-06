from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.llm.models import LLMRequest, LLMResponse


class LLMProvider(ABC):
    """Replaceable interface for a concrete LLM backend."""

    name: str

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        ...

    @abstractmethod
    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        ...

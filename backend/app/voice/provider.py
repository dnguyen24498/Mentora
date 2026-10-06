from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.voice.models import AudioChunk, SynthesisRequest, VoiceCloneRequest


class VoiceProvider(ABC):
    """Replaceable interface for a TTS engine (e.g. OmniVoice)."""

    name: str

    @abstractmethod
    async def create_voice(self, request: VoiceCloneRequest) -> str:
        ...

    @abstractmethod
    def synthesize(self, request: SynthesisRequest) -> AsyncIterator[AudioChunk]:
        ...

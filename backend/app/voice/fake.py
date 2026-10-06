from collections.abc import AsyncIterator

from app.voice.models import AudioChunk, SynthesisRequest, VoiceCloneRequest
from app.voice.provider import VoiceProvider


class FakeVoiceProvider(VoiceProvider):
    """Deterministic stub that emits empty audio chunks; no GPU or TTS engine required."""

    name = "fake-tts"

    async def create_voice(self, request: VoiceCloneRequest) -> str:
        return request.name

    async def synthesize(self, request: SynthesisRequest) -> AsyncIterator[AudioChunk]:
        for i, _chunk in enumerate(self._split(request.text)):
            yield AudioChunk(data=b"", sequence=i)

    @staticmethod
    def _split(text: str) -> list[str]:
        if not text:
            return []
        return [text[i : i + 200] for i in range(0, len(text), 200)]

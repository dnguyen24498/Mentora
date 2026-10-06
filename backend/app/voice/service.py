from collections.abc import AsyncIterator

from app.presentation.models import SlideDeck
from app.voice.models import AudioChunk, SynthesisRequest, VoiceCloneRequest
from app.voice.provider import VoiceProvider


class VoiceService:
    """Orchestrates TTS: resolves voice profile, chunks text, streams audio.

    Kept provider-agnostic so OmniVoice is replaceable. Audio chunks are
    streamed directly to callers and never pushed onto the general message bus.
    """

    def __init__(self, provider: VoiceProvider, max_chunk_chars: int = 400) -> None:
        self._provider = provider
        self._max_chunk_chars = max_chunk_chars

    async def create_teacher_voice(self, request: VoiceCloneRequest) -> str:
        """Clone a teacher's voice and return its voice profile id."""
        return await self._provider.create_voice(request)

    def chunk_text(self, text: str) -> list[str]:
        if not text:
            return []
        sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
        chunks: list[str] = []
        current = ""
        for sentence in sentences:
            candidate = f"{sentence}. "
            if len(current) + len(candidate) > self._max_chunk_chars and current:
                chunks.append(current.rstrip())
                current = candidate
            else:
                current += candidate
        if current.strip():
            chunks.append(current.rstrip())
        return chunks

    async def synthesize(self, request: SynthesisRequest) -> AsyncIterator[AudioChunk]:
        sequence = 0
        for chunk in self.chunk_text(request.text):
            sub_request = request.model_copy(update={"text": chunk})
            async for audio in self._provider.synthesize(sub_request):
                yield audio.model_copy(update={"sequence": sequence})
                sequence += 1

    async def speak_deck(self, deck: SlideDeck, voice_profile_id: str) -> AsyncIterator[AudioChunk]:
        """Speak every slide in order, streaming short chunks until the deck ends."""
        sequence = 0
        for slide in deck.slides:
            text = slide.content or slide.title
            request = SynthesisRequest(text=text, voice_profile_id=voice_profile_id)
            async for audio in self.synthesize(request):
                yield audio.model_copy(update={"sequence": sequence})
                sequence += 1

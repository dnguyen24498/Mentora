import pytest

from app.presentation.models import Slide, SlideDeck
from app.voice import FakeVoiceProvider, SynthesisRequest, VoiceService


def test_chunk_text_splits_long_input() -> None:
    service = VoiceService(FakeVoiceProvider(), max_chunk_chars=20)
    chunks = service.chunk_text("One sentence here. " + "Another sentence here. " * 5)
    assert len(chunks) > 1
    assert all(len(c) <= 20 + 5 for c in chunks)


async def test_synthesize_streams_sequential_chunks() -> None:
    service = VoiceService(FakeVoiceProvider(), max_chunk_chars=50)
    request = SynthesisRequest(text="Hello world. This is a second sentence.", voice_profile_id="vp1")
    chunks = [c async for c in service.synthesize(request)]
    assert chunks
    assert [c.sequence for c in chunks] == list(range(len(chunks)))
    assert all(c.sample_rate == 24000 for c in chunks)


async def test_empty_text_yields_no_audio() -> None:
    service = VoiceService(FakeVoiceProvider())
    request = SynthesisRequest(text="", voice_profile_id="vp1")
    chunks = [c async for c in service.synthesize(request)]
    assert chunks == []


async def test_speak_deck_iterates_slides_until_end() -> None:
    service = VoiceService(FakeVoiceProvider(), max_chunk_chars=100)
    deck = SlideDeck(
        document_id="deck1",
        slides=[
            Slide(index=1, title="Intro", content="Welcome to the lesson."),
            Slide(index=2, title="Body", content="Here is the core material."),
        ],
    )
    chunks = [c async for c in service.speak_deck(deck, voice_profile_id="vp1")]
    assert chunks
    assert chunks[0].sequence == 0
    assert chunks[-1].sequence == len(chunks) - 1

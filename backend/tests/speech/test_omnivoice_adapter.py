"""The OmniVoice prototype adapter against a fake sidecar (no network, no model)."""

from __future__ import annotations

import io
import urllib.error

from app.providers.factory import PROVIDER_OMNIVOICE, build_speech_service
from app.providers.omnivoice import OmniVoiceSettings, OmniVoiceSpeechProvider
from app.speech.models import SpeechOutcomeStatus, SpeechRequest
from app.speech.service import SpeechService


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _provider(opener):
    return OmniVoiceSpeechProvider(OmniVoiceSettings(base_url="http://sidecar"), opener=opener)


def test_pcm_from_the_sidecar_is_streamed_in_frames():
    pcm = b"\x01\x00" * 24_000  # one second at 24 kHz
    calls = []

    def opener(request, timeout):
        calls.append((request.full_url, request.data))
        return _Response(pcm)

    frames = []
    outcome = SpeechService(_provider(opener)).speak(
        SpeechRequest(text="Hello class.", generation=1), on_chunk=frames.append
    )
    assert outcome.status is SpeechOutcomeStatus.COMPLETED
    assert calls[0][0] == "http://sidecar/synthesize"
    assert b"Hello class." in calls[0][1]
    assert len(frames) == 10 and b"".join(f.audio for f in frames) == pcm
    assert frames[-1].final and outcome.segment.sample_rate == 24_000


def test_an_unreachable_sidecar_falls_back_to_text():
    def opener(request, timeout):
        raise urllib.error.URLError("connection refused")

    outcome = SpeechService(_provider(opener)).speak(SpeechRequest(text="Hello.", generation=2))
    assert outcome.status is SpeechOutcomeStatus.FALLBACK
    assert outcome.fallback.text == "Hello."


def test_a_sidecar_error_falls_back_to_text():
    def opener(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 500, "boom", {}, None)

    outcome = SpeechService(_provider(opener)).speak(SpeechRequest(text="Hi.", generation=3))
    assert outcome.status is SpeechOutcomeStatus.FALLBACK


def test_factory_selects_the_prototype_by_name():
    service = build_speech_service(PROVIDER_OMNIVOICE)
    identity = service.provider.identity()
    assert identity.name == "omnivoice" and "prototype" in identity.version
    assert service.config.sample_rate == 24_000

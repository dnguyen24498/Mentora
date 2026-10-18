"""The neutral-voice domain service: reserve, synthesize, cancel, fall back (V0-012).

Required tests (``TASK.md``): *"Mock contract, timeout, cancel twice, provider
error, fallback."* This file exercises the text fallback and the idempotent cancel
at the domain boundary, where a lesson would actually observe them.
"""

from __future__ import annotations

import logging

import pytest

from app.providers.deterministic import DeterministicSpeechProvider
from app.providers.factory import (
    UnknownSpeechProviderError,
    build_speech_service,
    create_speech_provider,
)
from app.speech.errors import SpeechErrorCode
from app.speech.models import (
    NEUTRAL_VOICE_ID,
    MarkerPlan,
    ReservationRequest,
    SpeechChunk,
    SpeechConfig,
    SpeechOutcomeStatus,
    SpeechRequest,
)
from app.speech.service import SpeechService
from app.speech.testing import ScriptedSpeechProvider
from tests.speech.helpers import MARKERS, UTTERANCE, FakeClock


def utterance_request(generation: int = 1, **kwargs) -> SpeechRequest:
    text = kwargs.pop("text", UTTERANCE)
    marker_plan = kwargs.pop("marker_plan", MARKERS)
    return SpeechRequest(
        text=text, generation=generation, marker_plan=marker_plan, **kwargs
    )


# -- the happy path --------------------------------------------------------------
def test_completed_synthesis_returns_audio_and_aggregates_usage():
    service = build_speech_service()
    outcome = service.speak(
        utterance_request(1, institution_id="inst-1")
    )

    assert outcome.status is SpeechOutcomeStatus.COMPLETED
    assert outcome.spoken and outcome.segment is not None
    assert outcome.segment.audio_bytes > 0
    assert [m.marker_id for m in outcome.segment.markers] == ["start", "middle", "end"]
    assert outcome.reservation_id is not None

    usage = service.usage()
    assert usage.characters == len(UTTERANCE)
    assert usage.audio_ms > 0 and usage.audio_bytes > 0
    assert service.health().total_synthesized == 1


def test_usage_accumulates_across_speak_calls():
    service = build_speech_service()
    service.speak(utterance_request(1))
    service.speak(utterance_request(2))
    assert service.usage().characters == 2 * len(UTTERANCE)
    assert service.health().total_synthesized == 2


def test_outcome_serializes_for_the_client():
    service = build_speech_service()
    payload = service.speak(utterance_request(3)).to_dict()
    assert payload["status"] == "COMPLETED"
    assert payload["segment"]["audio_bytes"] > 0
    assert payload["fallback"] is None


# -- fallback --------------------------------------------------------------------
def test_timeout_falls_back_to_text_and_does_not_block():
    clock = FakeClock()
    config = SpeechConfig(max_attempts=1)
    provider = ScriptedSpeechProvider(
        config=config, chunk_count=5, clock=clock, advance_per_chunk=0.2
    )
    service = SpeechService(provider, config=config)
    request = utterance_request(4, deadline_seconds=0.35, institution_id="inst-1")

    outcome = service.speak(request, clock=clock)

    assert outcome.status is SpeechOutcomeStatus.FALLBACK
    assert outcome.error_code is SpeechErrorCode.SYNTHESIS_TIMEOUT
    # The lesson continues on the text, and the semantic markers come with it.
    assert outcome.fallback is not None
    assert outcome.fallback.text == UTTERANCE
    assert outcome.fallback.reason is SpeechErrorCode.SYNTHESIS_TIMEOUT
    assert [m.marker_id for m in outcome.fallback.markers] == ["start", "middle", "end"]
    # Capacity is never leaked, even on the failure path.
    assert provider.health().reservations_held == 0
    assert service.telemetry.metrics.text_fallbacks == 1


def test_provider_error_falls_back_to_text():
    provider = ScriptedSpeechProvider(raise_immediately=SpeechErrorCode.SYNTHESIS_FAILED)
    service = SpeechService(provider)

    outcome = service.speak(utterance_request(5))

    assert outcome.status is SpeechOutcomeStatus.FALLBACK
    assert outcome.error_code is SpeechErrorCode.SYNTHESIS_FAILED
    assert outcome.segment is None
    assert service.telemetry.metrics.generations_failed == 1


def test_reservation_denied_falls_back_without_touching_held_capacity():
    config = SpeechConfig(max_concurrent_reservations=1)
    provider = DeterministicSpeechProvider(config)
    service = SpeechService(provider, config=config)
    held = provider.reserve(ReservationRequest(estimated_characters=1))

    outcome = service.speak(utterance_request(6))

    assert outcome.status is SpeechOutcomeStatus.FALLBACK
    assert outcome.error_code is SpeechErrorCode.RESERVATION_DENIED
    assert outcome.reservation_id is None
    # The reservation that was already held is untouched by the refusal.
    assert provider.health().reservations_held == 1
    assert service.telemetry.metrics.reservations_denied == 1
    provider.release(held.reservation_id)


def test_unauthorized_voice_routes_to_the_neutral_voice():
    provider = ScriptedSpeechProvider()
    service = SpeechService(provider)

    outcome = service.speak(utterance_request(7, voice_id="cloned-9"))

    assert outcome.status is SpeechOutcomeStatus.COMPLETED
    assert outcome.segment is not None
    assert outcome.segment.voice_id == NEUTRAL_VOICE_ID
    assert service.telemetry.metrics.voice_fallbacks == 1


# -- cancellation ----------------------------------------------------------------
def test_cancel_twice_through_the_service_is_idempotent():
    provider = ScriptedSpeechProvider(chunk_count=4)
    service = SpeechService(provider)
    request = utterance_request(8, institution_id="inst-1")
    acks = []

    def sink(chunk: SpeechChunk) -> None:
        if chunk.sequence == 0:
            acks.append(service.cancel(request.generation, institution_id="inst-1"))

    outcome = service.speak(request, on_chunk=sink)

    assert outcome.status is SpeechOutcomeStatus.CANCELLED
    assert outcome.error_code is SpeechErrorCode.CANCELLED
    assert acks[0].acknowledged is True and acks[0].duplicate is False

    again = service.cancel(request.generation)
    assert again.duplicate is True and again.acknowledged is True

    assert service.telemetry.metrics.cancel_acks == 1
    assert service.telemetry.metrics.cancel_replays == 1


def test_release_happens_on_every_terminal_path():
    completed = build_speech_service()
    completed.speak(utterance_request(9))

    failing_provider = ScriptedSpeechProvider(
        raise_immediately=SpeechErrorCode.SYNTHESIS_FAILED
    )
    falling_back = SpeechService(failing_provider)
    falling_back.speak(utterance_request(10))

    assert completed.health().reservations_held == 0
    assert completed.telemetry.metrics.reservations_released == 1
    assert failing_provider.health().reservations_held == 0
    assert falling_back.telemetry.metrics.reservations_released == 1


# -- observability ---------------------------------------------------------------
def test_telemetry_redacts_the_spoken_text(caplog):
    secret = "SECRET-PHRASE-MUST-NOT-BE-LOGGED"
    caplog.set_level(logging.INFO, logger="mentora.speech")

    service = build_speech_service()
    service.speak(utterance_request(11, text=f"{UTTERANCE} {secret}"))

    falling_back = SpeechService(
        ScriptedSpeechProvider(raise_immediately=SpeechErrorCode.SYNTHESIS_FAILED)
    )
    falling_back.speak(utterance_request(12, text=f"{UTTERANCE} {secret}"))

    assert caplog.records
    for record in caplog.records:
        assert secret not in record.getMessage()
    # Size is recorded instead, so cost stays observable without logging the text.
    assert any("characters" in record.getMessage() for record in caplog.records)


def test_health_reports_circuit_and_counters():
    service = build_speech_service()
    health = service.health()
    assert health.provider == "neutral-deterministic"
    assert health.voice_id == NEUTRAL_VOICE_ID
    assert health.state == "closed" and health.healthy is True
    assert health.to_dict()["capacity_units"] == 2


# -- factory ---------------------------------------------------------------------
def test_factory_builds_the_deterministic_provider_and_rejects_unknown_names():
    provider = create_speech_provider()
    assert provider.provider_id == "neutral-deterministic"
    assert provider.identity().name == "neutral-deterministic"

    with pytest.raises(UnknownSpeechProviderError):
        create_speech_provider("vendor-x")


def test_invalid_request_still_returns_a_terminal_outcome():
    # A malformed request (here, a duplicate marker id) is classified rather than
    # raised out of speak(): every terminal path is user-visible and observable.
    plan = MarkerPlan(markers=MARKERS.markers + (MARKERS.markers[0],))
    service = build_speech_service()
    outcome = service.speak(utterance_request(13, marker_plan=plan))
    assert outcome.status is SpeechOutcomeStatus.FALLBACK
    assert outcome.error_code is SpeechErrorCode.INVALID_REQUEST
    assert outcome.fallback is not None

"""The neutral-voice port contract and the deterministic adapter (V0-012).

Required tests (``TASK.md``): *"Mock contract, timeout, cancel twice, provider error,
fallback."* This file covers the contract, the timeout, the idempotent cancel and
the provider-error paths at the provider boundary; ``test_speech_service.py``
covers the text fallback at the domain boundary.
"""

from __future__ import annotations

import pytest

from app.providers.deterministic import DeterministicSpeechProvider, chunk_ranges
from app.speech.errors import SpeechError, SpeechErrorCode
from app.speech.models import (
    NEUTRAL_VOICE_ID,
    ReservationRequest,
    SpeechChunk,
    SpeechConfig,
    SpeechRequest,
    VoiceState,
)
from app.speech.port import SpeechBudget, SpeechProvider
from app.speech.testing import ScriptedSpeechProvider
from tests.speech.helpers import MARKERS, UTTERANCE, FakeClock


def deterministic() -> DeterministicSpeechProvider:
    return DeterministicSpeechProvider(SpeechConfig(deadline_seconds=1.0, max_attempts=1))


def scripted(**kwargs) -> ScriptedSpeechProvider:
    config = kwargs.pop("config", SpeechConfig(deadline_seconds=1.0, max_attempts=1))
    return ScriptedSpeechProvider(config=config, **kwargs)


def request(generation: int = 1, **kwargs) -> SpeechRequest:
    text = kwargs.pop("text", UTTERANCE)
    marker_plan = kwargs.pop("marker_plan", MARKERS)
    return SpeechRequest(
        text=text, generation=generation, marker_plan=marker_plan, **kwargs
    )


def run(
    provider: SpeechProvider,
    req: SpeechRequest,
    *,
    budget: SpeechBudget | None = None,
    on_chunk=None,
):
    """Synthesize and collect the streamed chunks for inspection."""

    chunks: list[SpeechChunk] = []
    budget = budget or SpeechBudget(req.deadline_seconds, max_attempts=1)

    def sink(chunk: SpeechChunk) -> None:
        chunks.append(chunk)
        if on_chunk is not None:
            on_chunk(chunk)

    segment = provider.synthesize(req, budget=budget, on_chunk=sink)
    return segment, chunks


# -- the shared port contract ----------------------------------------------------
@pytest.mark.parametrize("factory", [deterministic, scripted], ids=["deterministic", "scripted"])
def test_port_identity_health_and_usage(factory):
    provider = factory()
    identity = provider.identity()
    assert identity.name == provider.provider_id
    assert identity.config_hash

    segment, chunks = run(provider, request(1))
    assert segment.status is VoiceState.COMPLETED
    assert chunks and chunks[-1].final is True
    assert segment.usage.characters == len(UTTERANCE)
    assert segment.usage.audio_bytes == sum(c.byte_size for c in chunks)

    health = provider.health()
    assert health.healthy and health.state == "closed"
    assert health.total_synthesized == 1 and health.reservations_held == 0


@pytest.mark.parametrize("factory", [deterministic, scripted], ids=["deterministic", "scripted"])
def test_markers_are_realized_once_and_in_text_order(factory):
    segment, _ = run(factory(), request(1))
    assert [m.marker_id for m in segment.markers] == ["start", "middle", "end"]
    offsets = [m.offset_ms for m in segment.markers]
    assert offsets == sorted(offsets)


@pytest.mark.parametrize("factory", [deterministic, scripted], ids=["deterministic", "scripted"])
def test_capacity_is_bounded_and_release_is_idempotent(factory):
    provider = factory()  # default max_concurrent_reservations == 2
    first = provider.reserve(ReservationRequest(estimated_characters=10))
    second = provider.reserve(ReservationRequest(estimated_characters=10))
    assert first.reservation_id != second.reservation_id
    assert provider.health().reservations_held == 2

    with pytest.raises(SpeechError) as exc:
        provider.reserve(ReservationRequest(estimated_characters=10))
    assert exc.value.code is SpeechErrorCode.RESERVATION_DENIED

    provider.release(first.reservation_id)
    provider.release(first.reservation_id)  # idempotent: a replay is a no-op
    provider.release("never-held")  # unknown ids are a no-op too
    assert provider.health().reservations_held == 1
    provider.release(second.reservation_id)
    assert provider.health().reservations_held == 0


# -- the deterministic adapter ---------------------------------------------------
def test_deterministic_audio_is_stable_and_content_addressed():
    _, chunks_a = run(deterministic(), request(1))
    _, chunks_b = run(deterministic(), request(1))
    assert [c.audio for c in chunks_a] == [c.audio for c in chunks_b]

    # A different generation of the same text speaks the same words identically.
    provider = deterministic()
    _, first = run(provider, request(2))
    _, second = run(provider, request(3))
    assert [c.audio for c in first] == [c.audio for c in second]


def test_unauthorized_voice_is_refused():
    with pytest.raises(SpeechError) as exc:
        run(deterministic(), request(1, voice_id="cloned-9"))
    assert exc.value.code is SpeechErrorCode.VOICE_NOT_AUTHORIZED


def test_invalid_request_is_refused():
    provider = deterministic()
    budget = SpeechBudget(1.0, max_attempts=1)
    with pytest.raises(SpeechError) as empty:
        provider.synthesize(request(1, text="   "), budget=budget)
    assert empty.value.code is SpeechErrorCode.INVALID_REQUEST

    with pytest.raises(SpeechError) as generation:
        provider.synthesize(request(0), budget=budget)
    assert generation.value.code is SpeechErrorCode.INVALID_REQUEST

    small = DeterministicSpeechProvider(SpeechConfig(max_characters=8))
    with pytest.raises(SpeechError) as oversized:
        small.synthesize(request(1), budget=SpeechBudget(1.0))
    assert oversized.value.code is SpeechErrorCode.INVALID_REQUEST


def test_chunk_ranges_cover_the_text_without_gaps():
    assert chunk_ranges("abcdefg", 3) == [(0, 3), (3, 6), (6, 7)]
    assert chunk_ranges("ab", 3) == [(0, 2)]
    assert chunk_ranges("", 3) == []


def test_config_hash_is_stable_and_sensitive():
    assert SpeechConfig().config_hash() == SpeechConfig().config_hash()
    assert SpeechConfig().config_hash() != SpeechConfig(chunk_characters=8).config_hash()


# -- cancellation ----------------------------------------------------------------
def test_cancel_interrupts_the_stream_and_twice_is_idempotent():
    provider = scripted(chunk_count=3)
    req = request(11)
    acks = []

    def sink(chunk: SpeechChunk) -> None:
        if chunk.sequence == 0:
            acks.append(provider.cancel(req.generation))

    segment, chunks = run(provider, req, on_chunk=sink)

    assert segment.status is VoiceState.CANCELLED
    assert len(chunks) == 1  # the stream stopped at the next chunk boundary

    first = acks[0]
    assert first.acknowledged is True and first.duplicate is False
    assert first.status == VoiceState.CANCELLING.value

    again = provider.cancel(req.generation)
    assert again.acknowledged is True and again.duplicate is True
    assert again.status == VoiceState.CANCELLING.value

    third = provider.cancel(req.generation)  # a third replay is still a replay
    assert third.duplicate is True
    assert provider.health().total_cancelled == 1


def test_cancel_of_an_unknown_generation_is_not_acknowledged():
    provider = deterministic()
    ack = provider.cancel(999)
    assert ack.acknowledged is False and ack.duplicate is False
    assert ack.status == VoiceState.IDLE.value


def test_cancel_after_completion_reports_the_terminal_state():
    provider = deterministic()
    run(provider, request(4))
    ack = provider.cancel(4)
    assert ack.acknowledged is False and ack.status == VoiceState.COMPLETED.value


# -- provider errors, retry and the deadline -------------------------------------
def test_provider_error_after_audio_is_classified_and_not_retried():
    provider = scripted(chunk_count=4, fail_after_chunks=2, fail_code=SpeechErrorCode.SYNTHESIS_FAILED)
    segment, chunks = run(provider, request(3), budget=SpeechBudget(10.0, max_attempts=3))
    assert segment.status is VoiceState.FAILED
    assert segment.error_code is SpeechErrorCode.SYNTHESIS_FAILED
    assert segment.attempts == 1  # audio already left this attempt: no duplicate stream
    assert len(chunks) == 2 and provider.stream_calls == 1


def test_transient_failure_before_audio_is_retried_within_budget():
    provider = scripted(chunk_count=3, fail_after_chunks=0, fail_code=SpeechErrorCode.SYNTHESIS_TIMEOUT)
    segment, chunks = run(provider, request(4), budget=SpeechBudget(10.0, max_attempts=3))
    assert segment.error_code is SpeechErrorCode.SYNTHESIS_TIMEOUT
    assert segment.attempts == 3 and provider.stream_calls == 3
    assert chunks == []  # nothing was emitted before the failure


def test_permanent_error_is_not_retried():
    provider = scripted(raise_immediately=SpeechErrorCode.SYNTHESIS_FAILED)
    segment, _ = run(provider, request(5), budget=SpeechBudget(10.0, max_attempts=3))
    assert segment.error_code is SpeechErrorCode.SYNTHESIS_FAILED
    assert segment.attempts == 1 and provider.stream_calls == 1


def test_deadline_is_enforced_between_chunks():
    clock = FakeClock()
    provider = scripted(chunk_count=5, clock=clock, advance_per_chunk=0.2)
    budget = SpeechBudget(0.35, max_attempts=1, clock=clock)
    segment, chunks = run(provider, request(6), budget=budget)
    assert segment.status is VoiceState.FAILED
    assert segment.error_code is SpeechErrorCode.SYNTHESIS_TIMEOUT
    assert segment.chunk_count == 1 and len(chunks) == 1


def test_pre_expired_budget_fails_without_touching_the_provider():
    clock = FakeClock(now=5.0)
    provider = scripted()
    segment, chunks = run(provider, request(7), budget=SpeechBudget(0.0, clock=clock))
    assert segment.error_code is SpeechErrorCode.SYNTHESIS_TIMEOUT
    assert segment.chunk_count == 0 and chunks == [] and provider.stream_calls == 0


# -- circuit breaker / idempotent replay -----------------------------------------
def test_circuit_breaker_opens_and_refuses_admission():
    provider = scripted(
        raise_immediately=SpeechErrorCode.SYNTHESIS_FAILED,
        config=SpeechConfig(circuit_failure_threshold=1),
    )
    segment, _ = run(provider, request(1))
    assert segment.status is VoiceState.FAILED
    assert provider.health().state == "open"
    assert provider.health().healthy is False

    with pytest.raises(SpeechError) as exc:
        run(provider, request(2))
    assert exc.value.code is SpeechErrorCode.PROVIDER_UNAVAILABLE


def test_replayed_generation_returns_the_stored_verdict():
    provider = scripted(chunk_count=2)
    first, _ = run(provider, request(9))
    second, chunks = run(provider, request(9))
    assert second is first
    assert provider.stream_calls == 1
    assert chunks == []


def test_neutral_voice_is_the_only_authorized_voice():
    provider = deterministic()
    assert provider.authorize_voice(NEUTRAL_VOICE_ID).authorized is True
    assert provider.authorize_voice("mentora-cloned").authorized is False

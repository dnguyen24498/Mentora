"""One server-sent narration stream (V0-013).

The transport is a newline-delimited JSON stream. Each line is one semantic event:
the script metadata, the caption, one complete WAV segment, zero or more marker
realizations, and the terminal verdict. Audio is base64 inside the JSON envelope
because the timeline events carry both metadata and bytes; a production media
plane will move audio over the SFU instead (V1-005, ``DEC-TECH-004`` is ``OPEN``).

The synthesis loop is a worker thread behind a bounded queue, not a generator that
blocks the HTTP response. That shape is what makes cancellation meaningful: when
the client goes away or the teacher changes slide, the stream's ``finally`` sets
the cancel token and calls the provider's idempotent ``cancel`` for every active
generation. The provider's own deadline/retry/fallback rules are not reimplemented
here.

The neutral adapter is a deterministic local mock, so the audio is tones rather
than intelligible speech. It is labelled as such in the stream metadata; the code
is the same path a real provider will use once ``DEC-TECH-007`` is decided.
"""

from __future__ import annotations

import base64
import hashlib
import json
import queue
import threading
import time
from typing import Any, Callable, Iterable, Iterator, Optional

from app.classroom.timeline.controller import (
    ChunkDisposition,
    MarkerDisposition,
    TimelineController,
)
from app.classroom.timeline.models import NarrationScript, TimelineStatus
from app.classroom.timeline.telemetry import TimelineTelemetry
from app.speech.models import (
    MarkerPlan,
    SpeechOutcomeStatus,
    SpeechRequest,
    TextFallback,
)
from app.speech.port import CancelToken
from app.speech.service import SpeechService


def wav_bytes(
    pcm: bytes, *, sample_rate: int, bytes_per_sample: int, channels: int = 1
) -> bytes:
    """Wrap raw PCM frames in a canonical RIFF/WAVE container.

    The neutral adapter streams headerless frames. A browser can play a WAV blob
    without a decoder dependency, and the header describes exactly one semantic
    chunk, so the client never has to concatenate across a boundary.
    """

    sample_rate = max(1, int(sample_rate))
    bytes_per_sample = max(1, int(bytes_per_sample))
    channels = max(1, int(channels))
    byte_rate = sample_rate * channels * bytes_per_sample
    block_align = channels * bytes_per_sample
    header = b"RIFF" + (36 + len(pcm)).to_bytes(4, "little") + b"WAVE"
    header += b"fmt " + (16).to_bytes(4, "little") + (1).to_bytes(2, "little")
    header += channels.to_bytes(2, "little") + sample_rate.to_bytes(4, "little")
    header += byte_rate.to_bytes(4, "little") + block_align.to_bytes(2, "little")
    header += (8 * bytes_per_sample).to_bytes(2, "little")
    header += b"data" + len(pcm).to_bytes(4, "little")
    return header + pcm


def _json_line(event: dict[str, Any]) -> str:
    return json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


class NarrationStreamer:
    """Turn one :class:`NarrationScript` into ordered stream events."""

    def __init__(
        self,
        speech: SpeechService,
        *,
        telemetry: Optional[TimelineTelemetry] = None,
        clock: Callable[[], float] = time.monotonic,
        queue_size: int = 64,
        generation_base: Optional[int] = None,
    ) -> None:
        self._speech = speech
        self._telemetry = telemetry or TimelineTelemetry()
        self._clock = clock
        self._queue_size = max(1, int(queue_size))
        self._generation_base = generation_base

    # -- public: a streaming iterator of JSON-ready events -----------------------
    def iter_events(
        self,
        *,
        institution_id: str,
        class_id: str,
        session_id: str,
        actor_epoch: int,
        state_version: int,
        script: NarrationScript,
        cancel: Optional[CancelToken] = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield events until the segment completes, falls back, or is cancelled.

        The caller is responsible for serialising each event (``json_line``). The
        worker is cancelled if the consumer closes this iterator, so a browser
        navigation or a slide change does not leak a provider reservation.
        """

        base_generation = self._generation_base or self._new_generation(
            class_id=class_id,
            scene_id=script.scene_id,
            actor_epoch=actor_epoch,
            state_version=state_version,
        )
        controller = TimelineController(clock=lambda: _datetime_now())
        controller.begin(
            generation=base_generation,
            actor_epoch=actor_epoch,
            scene_id=script.scene_id,
        )

        q: "queue.Queue[Any]" = queue.Queue(maxsize=self._queue_size)
        stop = threading.Event()
        token = cancel or CancelToken()
        active_generations: set[int] = set()
        sequence = 0
        sequence_lock = threading.Lock()

        provider = self._speech.provider.identity().to_dict()

        def emit(event: dict[str, Any]) -> bool:
            nonlocal sequence
            with sequence_lock:
                sequence += 1
                line = {
                    "schema_version": "1.0",
                    "sequence": sequence,
                    "class_id": class_id,
                    "session_id": session_id,
                    "scene_id": script.scene_id,
                    "actor_epoch": actor_epoch,
                    "state_version": state_version,
                    "generation": base_generation,
                    **event,
                }
            while not stop.is_set():
                try:
                    q.put(line, timeout=0.1)
                    return True
                except queue.Full:
                    continue
            return False

        def put_final() -> None:
            while not stop.is_set():
                try:
                    q.put(_SENTINEL, timeout=0.1)
                    return
                except queue.Full:
                    continue

        def cancel_active() -> None:
            token.cancel()
            for generation in tuple(active_generations):
                try:
                    self._speech.cancel(generation, institution_id=institution_id)
                except Exception:  # cancellation is best effort and idempotent
                    pass

        def work() -> None:
            total_ms = 0
            try:
                self._telemetry.record_started(
                    institution_id=institution_id,
                    class_id=class_id,
                    session_id=session_id,
                    scene_id=script.scene_id,
                    source=script.source.value,
                    chunk_count=script.chunk_count,
                    word_count=script.word_count,
                    provider=str(provider.get("name", "")),
                    voice_id=script.voice_id,
                    actor_epoch=actor_epoch,
                    state_version=state_version,
                )
                emit(
                    {
                        "type": "narration.started",
                        "source": script.source.value,
                        "chunk_count": script.chunk_count,
                        "word_count": script.word_count,
                        "voice_id": script.voice_id,
                        "language": script.language,
                        "provider": provider,
                        "empty": script.empty,
                    }
                )
                if script.empty:
                    controller.complete()
                    self._telemetry.record_completed(
                        institution_id=institution_id,
                        class_id=class_id,
                        scene_id=script.scene_id,
                        status="EMPTY",
                        duration_ms=0,
                    )
                    emit(
                        {
                            "type": "narration.completed",
                            "status": "EMPTY",
                            "duration_ms": 0,
                            "fallback": False,
                            "checkpoint": controller.checkpoint(label="narration-empty").to_dict(),
                        }
                    )
                    return

                for chunk in script.chunks:
                    if stop.is_set() or token.cancelled:
                        break

                    chunk_generation = base_generation + chunk.index
                    active_generations.add(chunk_generation)
                    controller.begin_segment(chunk.index)
                    marker_plan = MarkerPlan(markers=chunk.marker_plan())
                    emit(
                        {
                            "type": "segment.started",
                            "chunk_index": chunk.index,
                            "chunk_count": script.chunk_count,
                            "marker_ids": list(chunk.marker_ids),
                        }
                    )
                    # The caption is authored text, not generated text. It is sent
                    # for accessibility and for the fallback UI; the classroom
                    # surface hides it unless the viewer asks for it.
                    emit(
                        {
                            "type": "caption",
                            "chunk_index": chunk.index,
                            "text": chunk.text,
                            "marker_ids": list(chunk.marker_ids),
                        }
                    )

                    audio = bytearray()

                    def on_chunk(frame) -> None:
                        if stop.is_set() or token.cancelled:
                            token.cancel()
                            return
                        audio.extend(frame.audio)

                    request = SpeechRequest(
                        text=chunk.text,
                        generation=chunk_generation,
                        voice_id=script.voice_id,
                        language=script.language,
                        marker_plan=marker_plan,
                        deadline_seconds=self._speech.config.deadline_seconds,
                        institution_id=institution_id,
                        correlation_id=f"{class_id}:{script.scene_id}:{chunk.index}",
                    )
                    outcome = self._speech.speak(
                        request, on_chunk=on_chunk, cancel=token
                    )

                    if outcome.status is SpeechOutcomeStatus.CANCELLED:
                        controller.cancel()
                        self._telemetry.record_completed(
                            institution_id=institution_id,
                            class_id=class_id,
                            scene_id=script.scene_id,
                            status="CANCELLED",
                            duration_ms=total_ms,
                        )
                        emit(
                            {
                                "type": "narration.cancelled",
                                "status": "CANCELLED",
                                "duration_ms": total_ms,
                                "checkpoint": controller.checkpoint(
                                    label="narration-cancelled"
                                ).to_dict(),
                            }
                        )
                        break

                    if outcome.fell_back:
                        fallback = outcome.fallback or TextFallback(
                            text=chunk.text,
                            language=script.language,
                            markers=(),
                            reason=outcome.error_code or _fallback_reason(),
                        )
                        controller.fallback()
                        self._telemetry.record_segment(
                            institution_id=institution_id,
                            class_id=class_id,
                            scene_id=script.scene_id,
                            chunk_index=chunk.index,
                            status="FALLBACK",
                            reason=fallback.reason.value,
                        )
                        self._telemetry.record_completed(
                            institution_id=institution_id,
                            class_id=class_id,
                            scene_id=script.scene_id,
                            status="FALLBACK",
                            duration_ms=total_ms,
                            fallback=True,
                        )
                        emit(
                            {
                                "type": "segment.fallback",
                                "chunk_index": chunk.index,
                                "text": fallback.text,
                                "reason": fallback.reason.value,
                                "marker_ids": [m.marker_id for m in fallback.markers],
                            }
                        )
                        emit(
                            {
                                "type": "narration.completed",
                                "status": "FALLBACK",
                                "duration_ms": total_ms,
                                "fallback": True,
                                "checkpoint": controller.checkpoint(
                                    label="narration-fallback", final=False
                                ).to_dict(),
                            }
                        )
                        break

                    if not audio:
                        # A "completed" synthesis with no frames is not playable;
                        # treat it as the text fallback rather than a silent gap.
                        fallback = TextFallback(
                            text=chunk.text,
                            language=script.language,
                            markers=(),
                            reason=outcome.error_code or _fallback_reason(),
                        )
                        controller.fallback()
                        self._telemetry.record_segment(
                            institution_id=institution_id,
                            class_id=class_id,
                            scene_id=script.scene_id,
                            chunk_index=chunk.index,
                            status="FALLBACK",
                            reason=fallback.reason.value,
                        )
                        self._telemetry.record_completed(
                            institution_id=institution_id,
                            class_id=class_id,
                            scene_id=script.scene_id,
                            status="FALLBACK",
                            duration_ms=total_ms,
                            fallback=True,
                        )
                        emit(
                            {
                                "type": "segment.fallback",
                                "chunk_index": chunk.index,
                                "text": fallback.text,
                                "reason": fallback.reason.value,
                                "marker_ids": [],
                            }
                        )
                        emit(
                            {
                                "type": "narration.completed",
                                "status": "FALLBACK",
                                "duration_ms": total_ms,
                                "fallback": True,
                                "checkpoint": controller.checkpoint(
                                    label="narration-fallback", final=False
                                ).to_dict(),
                            }
                        )
                        break

                    segment = outcome.segment
                    if segment is not None:
                        wav = wav_bytes(
                            bytes(audio),
                            sample_rate=segment.sample_rate or 8000,
                            bytes_per_sample=segment.bytes_per_sample or 2,
                            channels=segment.channels or 1,
                        )
                        emit(
                            {
                                "type": "audio",
                                "chunk_index": chunk.index,
                                "content_type": "audio/wav",
                                "sample_rate": sample_rate_of(segment),
                                "bytes_per_sample": bytes_per_sample_of(segment),
                                "channels": channels_of(segment),
                                "duration_ms": segment.duration_ms,
                                "audio_bytes": len(wav),
                                "data": base64.b64encode(wav).decode("ascii"),
                            }
                        )
                        for marker in segment.markers:
                            disposition = controller.accept_marker(
                                generation=base_generation,
                                marker_id=marker.marker_id,
                                offset_ms=marker.offset_ms,
                            )
                            if disposition is MarkerDisposition.ACCEPTED:
                                emit(
                                    {
                                        "type": "marker",
                                        "chunk_index": chunk.index,
                                        "marker_id": marker.marker_id,
                                        "offset_ms": marker.offset_ms,
                                    }
                                )
                            elif disposition is MarkerDisposition.DUPLICATE:
                                self._telemetry.record_duplicate_marker(
                                    class_id=class_id,
                                    scene_id=script.scene_id,
                                    marker_id=marker.marker_id,
                                )
                            elif disposition is MarkerDisposition.LATE:
                                self._telemetry.record_late_marker(
                                    class_id=class_id,
                                    scene_id=script.scene_id,
                                    marker_id=marker.marker_id,
                                )
                            else:
                                self._telemetry.record_stale_event(
                                    class_id=class_id,
                                    scene_id=script.scene_id,
                                    kind="marker",
                                )
                        disposition = controller.accept_chunk(
                            generation=base_generation,
                            # One playable WAV per semantic chunk: the provider's
                            # own frame sequence is internal to that synthesis.
                            sequence=0,
                            duration_ms=segment.duration_ms,
                        )
                        if disposition is ChunkDisposition.ACCEPTED:
                            total_ms += max(0, segment.duration_ms)
                        elif disposition is ChunkDisposition.DUPLICATE:
                            self._telemetry.record_stale_event(
                                class_id=class_id, scene_id=script.scene_id, kind="duplicate_chunk"
                            )
                        else:
                            self._telemetry.record_stale_event(
                                class_id=class_id, scene_id=script.scene_id, kind="chunk"
                            )
                        self._telemetry.record_segment(
                            institution_id=institution_id,
                            class_id=class_id,
                            scene_id=script.scene_id,
                            chunk_index=chunk.index,
                            status="COMPLETED",
                            audio_ms=segment.duration_ms,
                            audio_bytes=len(wav),
                            marker_count=len(segment.markers),
                        )
                        emit(
                            {
                                "type": "segment.completed",
                                "chunk_index": chunk.index,
                                "status": "COMPLETED",
                                "audio_ms": segment.duration_ms,
                                "audio_bytes": len(wav),
                                "marker_count": len(segment.markers),
                            }
                        )
                    else:
                        controller.fail()
                        emit(
                            {
                                "type": "error",
                                "code": "NARRATION_FAILED",
                                "message": "speech completed without a segment",
                                "retryable": False,
                            }
                        )
                        break

                if controller.state.status is TimelineStatus.CANCELLED:
                    return
                if controller.state.status.terminal:
                    return
                controller.complete()
                self._telemetry.record_completed(
                    institution_id=institution_id,
                    class_id=class_id,
                    scene_id=script.scene_id,
                    status="COMPLETED",
                    duration_ms=total_ms,
                )
                emit(
                    {
                        "type": "narration.completed",
                        "status": "COMPLETED",
                        "duration_ms": total_ms,
                        "fallback": False,
                        "checkpoint": controller.checkpoint(
                            label="narration-complete", final=False
                        ).to_dict(),
                    }
                )
            except Exception as exc:  # a transport bug is classified, never a 500 mid-stream
                controller.fail()
                self._telemetry.record_completed(
                    institution_id=institution_id,
                    class_id=class_id,
                    scene_id=script.scene_id,
                    status="FAILED",
                    duration_ms=0,
                )
                emit(
                    {
                        "type": "error",
                        "code": "NARRATION_FAILED",
                        "message": str(exc),
                        "retryable": False,
                    }
                )
            finally:
                put_final()

        thread = threading.Thread(target=work, name=f"narration-{class_id}", daemon=True)
        thread.start()
        try:
            while True:
                item = q.get()
                if item is _SENTINEL:
                    break
                yield item
        finally:
            stop.set()
            cancel_active()
            # The worker notices ``stop`` at its next queue boundary. It is a
            # daemon thread, so a provider that ignores cancellation cannot keep
            # the process alive.
            thread.join(timeout=1.0)

    # -- helpers ----------------------------------------------------------------
    def _new_generation(
        self, *, class_id: str, scene_id: str, actor_epoch: int, state_version: int
    ) -> int:
        digest = hashlib.sha256(
            f"{class_id}\u001f{scene_id}\u001f{actor_epoch}\u001f{state_version}\u001f{time.time_ns()}".encode(
                "utf-8"
            )
        ).hexdigest()
        return max(1, int(digest[:8], 16))


class _Sentinel:
    pass


_SENTINEL = _Sentinel()


def _datetime_now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def _fallback_reason():
    from app.speech.errors import SpeechErrorCode

    return SpeechErrorCode.SYNTHESIS_FAILED


def sample_rate_of(segment) -> int:
    return int(getattr(segment, "sample_rate", 0) or 8000)


def bytes_per_sample_of(segment) -> int:
    return int(getattr(segment, "bytes_per_sample", 0) or 2)


def channels_of(segment) -> int:
    return int(getattr(segment, "channels", 0) or 1)


def json_line(event: dict[str, Any]) -> str:
    return _json_line(event)


__all__ = ["NarrationStreamer", "json_line", "wav_bytes"]

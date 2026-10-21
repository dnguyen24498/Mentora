"""Timeline narration: chunking, script precedence, controller and stream (V0-013)."""

from __future__ import annotations

import base64

import pytest

from app.classroom.scene_source import PinnedSceneSummary
from app.classroom.timeline import (
    ChunkDisposition,
    MarkerDisposition,
    NarrationSource,
    TimelineController,
    TimelineGapError,
    TimelineStatus,
    build_narration,
    split_text,
)
from app.classroom.timeline.stream import NarrationStreamer
from app.providers.factory import build_speech_service
from app.speech.errors import SpeechErrorCode
from app.speech.service import SpeechService
from app.speech.testing import ScriptedSpeechProvider


def _scene(*, notes=None, text=("Slide body",), scene_id="s1", order=0):
    return PinnedSceneSummary(
        order=order, scene_id=scene_id, fidelity="STRUCTURAL_RENDERED", notes=notes,
        text=tuple(text), warnings=(), object_count=1, step_count=1,
    )


# -- chunking -----------------------------------------------------------------------
def test_chunks_are_word_safe_and_bounded():
    text = " ".join(f"word{i}" for i in range(200))
    chunks = split_text(text, max_characters=60, min_characters=20)
    assert len(chunks) > 1
    words = text.split()
    assert [w for c in chunks for w in c.text.split()] == words
    for chunk in chunks:
        assert len(chunk.text) <= 60
        assert text[chunk.char_start:chunk.char_end] == chunk.text


def test_chunks_close_at_sentence_boundaries():
    text = "This first sentence is long enough to close. And the second one also closes here."
    chunks = split_text(text, max_characters=160, min_characters=20)
    assert [c.text for c in chunks] == [
        "This first sentence is long enough to close.",
        "And the second one also closes here.",
    ]


def test_long_token_is_kept_whole_and_empty_text_has_no_chunks():
    token = "x" * 300
    assert [c.text for c in split_text(f"a {token} b", max_characters=50)] == ["a", token, "b"]
    assert split_text("   ") == ()


# -- script precedence --------------------------------------------------------------
@pytest.mark.parametrize(
    "section, notes, expected",
    [
        ({"script": "Lesson words.", "fallback_script": "Fallback."}, "Notes.", NarrationSource.LESSON_SCRIPT),
        ({"fallback_script": "Fallback."}, "Notes.", NarrationSource.FALLBACK_SCRIPT),
        ({}, "Notes.", NarrationSource.SPEAKER_NOTES),
        ({}, None, NarrationSource.SLIDE_TEXT),
    ],
)
def test_narration_precedence(section, notes, expected):
    plan = {"sections": [{"scene_id": "s1", "safe_markers": ["s1#step-0"], **section}]}
    script = build_narration(scene=_scene(notes=notes), lesson_plan=plan)
    assert script.source is expected
    assert script.chunks[0].marker_ids == ("s1#step-0",)


def test_a_scene_without_text_is_an_explicit_empty_script():
    script = build_narration(scene=_scene(text=()), lesson_plan={"sections": []})
    assert script.empty and script.source is NarrationSource.NONE


# -- controller ---------------------------------------------------------------------
def _controller(generation=10):
    controller = TimelineController()
    controller.begin(generation=generation, actor_epoch=1, scene_id="s1")
    controller.begin_segment(0)
    return controller


def test_duplicate_and_late_markers_are_ignored():
    c = _controller()
    assert c.accept_marker(generation=10, marker_id="m1", offset_ms=100) is MarkerDisposition.ACCEPTED
    assert c.accept_marker(generation=10, marker_id="m1", offset_ms=100) is MarkerDisposition.DUPLICATE
    assert c.accept_marker(generation=10, marker_id="m2", offset_ms=50) is MarkerDisposition.LATE
    c.complete()
    assert c.accept_marker(generation=10, marker_id="m3", offset_ms=500) is MarkerDisposition.LATE


def test_old_generation_cannot_mutate_current():
    c = _controller()
    c.resume(generation=11)
    assert c.accept_chunk(generation=10, sequence=0, duration_ms=5) is ChunkDisposition.STALE
    assert c.accept_marker(generation=10, marker_id="m", offset_ms=0) is MarkerDisposition.STALE
    assert c.accept_chunk(generation=11, sequence=0, duration_ms=5) is ChunkDisposition.ACCEPTED


def test_duplicate_chunk_and_gap():
    c = _controller()
    assert c.accept_chunk(generation=10, sequence=0, duration_ms=5) is ChunkDisposition.ACCEPTED
    assert c.accept_chunk(generation=10, sequence=0, duration_ms=5) is ChunkDisposition.DUPLICATE
    with pytest.raises(TimelineGapError):
        c.accept_chunk(generation=10, sequence=2, duration_ms=5)


def test_checkpoint_before_cancel_and_resume_at_semantic_segment():
    c = _controller()
    c.begin_segment(2)
    c.accept_chunk(generation=10, sequence=0, duration_ms=300)
    checkpoint = c.checkpoint(label="pause")
    c.cancel()
    assert checkpoint.segment_index == 2 and checkpoint.offset_ms == 300
    state = c.resume(generation=11)
    assert state.status is TimelineStatus.SYNTHESIZING
    assert state.segment_index == 2 and state.played_ms == 0


# -- stream -------------------------------------------------------------------------
PLAN = {"sections": [{"scene_id": "s1", "safe_markers": ["s1#step-0"],
                      "script": "First sentence is here and long enough. Second sentence follows it now."}]}


def _events(speech: SpeechService, script=None):
    script = script or build_narration(scene=_scene(), lesson_plan=PLAN, min_characters=10)
    streamer = NarrationStreamer(speech, generation_base=100)
    return list(streamer.iter_events(
        institution_id="inst", class_id="c1", session_id="sess", actor_epoch=1,
        state_version=3, script=script,
    ))


def test_stream_emits_one_wav_per_chunk_and_completes():
    events = _events(build_speech_service())
    types = [e["type"] for e in events]
    assert types[0] == "narration.started" and types[-1] == "narration.completed"
    assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
    audio = [e for e in events if e["type"] == "audio"]
    assert len(audio) == 2
    assert base64.b64decode(audio[0]["data"])[:4] == b"RIFF"
    markers = [e for e in events if e["type"] == "marker"]
    assert [m["marker_id"] for m in markers] == ["s1#step-0"]
    assert events[-1]["status"] == "COMPLETED" and events[-1]["duration_ms"] > 0
    assert all(e["generation"] == 100 and e["actor_epoch"] == 1 for e in events)


def test_tts_without_marker_still_completes():
    plan = {"sections": [{"scene_id": "s1", "safe_markers": [], "script": "Just words."}]}
    script = build_narration(scene=_scene(), lesson_plan=plan)
    events = _events(build_speech_service(), script)
    assert not [e for e in events if e["type"] == "marker"]
    assert events[-1]["status"] == "COMPLETED"


def test_provider_failure_falls_back_to_text_and_ends_the_stream():
    provider = ScriptedSpeechProvider(raise_immediately=SpeechErrorCode.SYNTHESIS_FAILED)
    events = _events(SpeechService(provider))
    fallback = [e for e in events if e["type"] == "segment.fallback"]
    assert fallback and fallback[0]["text"].startswith("First sentence")
    assert events[-1]["type"] == "narration.completed"
    assert events[-1]["status"] == "FALLBACK" and events[-1]["fallback"] is True
    assert not [e for e in events if e["type"] == "audio"]


def test_empty_script_completes_as_empty():
    script = build_narration(scene=_scene(text=()), lesson_plan={"sections": []})
    events = _events(build_speech_service(), script)
    assert [e["type"] for e in events] == ["narration.started", "narration.completed"]
    assert events[-1]["status"] == "EMPTY"


def test_closing_the_stream_cancels_the_worker():
    script = build_narration(
        scene=_scene(), lesson_plan={"sections": [{"scene_id": "s1", "safe_markers": [],
                                                   "script": " ".join(["Sentence number here."] * 40)}]},
        min_characters=10,
    )
    streamer = NarrationStreamer(build_speech_service(), generation_base=500, queue_size=1)
    iterator = streamer.iter_events(
        institution_id="inst", class_id="c1", session_id="s", actor_epoch=1,
        state_version=1, script=script,
    )
    first = next(iterator)
    assert first["type"] == "narration.started"
    iterator.close()  # the client went away: no exception, worker stops

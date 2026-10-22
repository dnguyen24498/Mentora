"""The in-process live narration relay (V1-005 bridge)."""

from __future__ import annotations

from app.classroom.timeline.relay import NarrationRelay


INSTITUTION = "inst-1"
CLASS = "class-1"


def _base(**overrides):
    event = {
        "schema_version": "1.0",
        "sequence": 1,
        "class_id": CLASS,
        "session_id": "session-1",
        "scene_id": "slide-1",
        "actor_epoch": 1,
        "state_version": 3,
        "generation": 100,
        "type": "narration.started",
        "source": "slide-text",
        "chunk_count": 1,
        "word_count": 2,
        "voice_id": "neutral",
        "provider": {"name": "neutral-deterministic"},
        "empty": False,
    }
    event.update(overrides)
    return event


def _audio(**overrides):
    event = _base(
        **{
            "sequence": 2,
            "type": "audio",
            "chunk_index": 0,
            "content_type": "audio/wav",
            "duration_ms": 100,
            "data": "UklGRg==",
        }
    )
    event.update(overrides)
    return event


def _completed(**overrides):
    event = _base(
        **{
            "sequence": 3,
            "type": "narration.completed",
            "status": "COMPLETED",
            "duration_ms": 100,
            "fallback": False,
        }
    )
    event.update(overrides)
    return event


def test_idle_class_has_nothing_to_attach_to():
    relay = NarrationRelay()
    assert relay.attach(
        INSTITUTION, CLASS, actor_epoch=1, min_state_version=1
    ) is None
    assert relay.is_live(INSTITUTION, CLASS) is False


def test_attached_student_gets_the_start_then_live_chunks():
    relay = NarrationRelay()
    relay.publish(INSTITUTION, CLASS, _base())
    attachment = relay.attach(
        INSTITUTION, CLASS, actor_epoch=1, min_state_version=3
    )
    assert attachment is not None

    relay.publish(INSTITUTION, CLASS, _audio())
    relay.publish(INSTITUTION, CLASS, _completed())

    events = list(attachment.events())
    assert [event["type"] for event in events] == [
        "narration.started",
        "audio",
        "narration.completed",
    ]
    assert events[1]["data"] == "UklGRg=="
    assert relay.is_live(INSTITUTION, CLASS) is False
    # A completed generation stays replayable for a student who attached just
    # after the teacher's fast local synthesis finished the whole slide.
    replay = relay.attach(
        INSTITUTION, CLASS, actor_epoch=1, min_state_version=3
    )
    assert replay is not None
    assert [event["type"] for event in replay.events()] == [
        "narration.started",
        "audio",
        "narration.completed",
    ]
    # A page that has already consumed it passes `after_generation`, so waiting
    # for the next slide does not replay the one it just heard.
    assert relay.attach(
        INSTITUTION,
        CLASS,
        actor_epoch=1,
        min_state_version=3,
        after_generation=100,
    ) is None


def test_late_student_hears_the_current_slide_from_its_start():
    relay = NarrationRelay()
    relay.publish(INSTITUTION, CLASS, _base())
    # Already produced before the student attaches. The current slide is the unit
    # of replay, so this chunk must not be lost.
    relay.publish(INSTITUTION, CLASS, _audio())
    attachment = relay.attach(
        INSTITUTION, CLASS, actor_epoch=1, min_state_version=3
    )
    assert attachment is not None
    relay.publish(INSTITUTION, CLASS, _completed(sequence=4))

    events = list(attachment.events())
    assert [event["type"] for event in events] == [
        "narration.started",
        "audio",
        "narration.completed",
    ]
    assert events[1]["data"] == "UklGRg=="


def test_after_generation_only_blocks_that_exact_slide():
    relay = NarrationRelay()
    relay.publish(INSTITUTION, CLASS, _base())
    relay.publish(INSTITUTION, CLASS, _completed(sequence=2))
    assert relay.attach(
        INSTITUTION,
        CLASS,
        actor_epoch=1,
        min_state_version=3,
        after_generation=100,
    ) is None

    relay.publish(
        INSTITUTION,
        CLASS,
        _base(sequence=1, generation=200, scene_id="slide-2", state_version=4),
    )
    attachment = relay.attach(
        INSTITUTION,
        CLASS,
        actor_epoch=1,
        min_state_version=4,
        after_generation=100,
    )
    assert attachment is not None
    assert attachment.start_event["generation"] == 200
    attachment.close()


def test_a_completed_generation_expires_after_the_replay_ttl():
    relay = NarrationRelay(replay_ttl_seconds=0)
    relay.publish(INSTITUTION, CLASS, _base())
    relay.publish(INSTITUTION, CLASS, _completed(sequence=2))
    assert relay.attach(
        INSTITUTION, CLASS, actor_epoch=1, min_state_version=3
    ) is None


def test_expected_scene_id_keeps_the_audio_under_the_right_slide():
    relay = NarrationRelay()
    relay.publish(INSTITUTION, CLASS, _base(scene_id="slide-1"))
    assert relay.attach(
        INSTITUTION,
        CLASS,
        actor_epoch=1,
        min_state_version=3,
        expected_scene_id="slide-2",
    ) is None
    attachment = relay.attach(
        INSTITUTION,
        CLASS,
        actor_epoch=1,
        min_state_version=3,
        expected_scene_id="slide-1",
    )
    assert attachment is not None
    assert attachment.start_event["scene_id"] == "slide-1"
    attachment.close()


def test_finish_after_completion_leaves_the_slide_replayable():
    relay = NarrationRelay()
    relay.publish(INSTITUTION, CLASS, _base())
    relay.publish(INSTITUTION, CLASS, _completed(sequence=2))
    relay.finish(INSTITUTION, CLASS, 100)
    attachment = relay.attach(
        INSTITUTION, CLASS, actor_epoch=1, min_state_version=3
    )
    assert attachment is not None
    assert [event["type"] for event in attachment.events()] == [
        "narration.started",
        "narration.completed",
    ]


def test_a_new_generation_cancels_the_old_subscription():
    relay = NarrationRelay()
    relay.publish(INSTITUTION, CLASS, _base())
    attachment = relay.attach(
        INSTITUTION, CLASS, actor_epoch=1, min_state_version=3
    )
    assert attachment is not None
    relay.publish(INSTITUTION, CLASS, _audio())

    relay.publish(
        INSTITUTION,
        CLASS,
        _base(
            sequence=1,
            generation=200,
            scene_id="slide-2",
            state_version=4,
        ),
    )
    old_events = list(attachment.events())
    assert [event["type"] for event in old_events] == [
        "narration.started",
        "audio",
        "narration.cancelled",
    ]
    assert old_events[-1]["generation"] == 100
    assert old_events[-1]["status"] == "CANCELLED"
    # The synthetic verdict keeps the event contract's required envelope; it does
    # not smuggle the last chunk's audio/text into a cancellation.
    for key in (
        "schema_version",
        "sequence",
        "class_id",
        "session_id",
        "scene_id",
        "actor_epoch",
        "state_version",
        "generation",
    ):
        assert key in old_events[-1]
    assert "data" not in old_events[-1]

    current = relay.attach(
        INSTITUTION, CLASS, actor_epoch=1, min_state_version=4
    )
    assert current is not None
    assert current.start_event["generation"] == 200
    current.close()


def test_finish_without_a_terminal_sends_a_cancellation():
    relay = NarrationRelay()
    relay.publish(INSTITUTION, CLASS, _base())
    attachment = relay.attach(
        INSTITUTION, CLASS, actor_epoch=1, min_state_version=3
    )
    assert attachment is not None

    relay.finish(INSTITUTION, CLASS, 100)
    events = list(attachment.events())
    assert [event["type"] for event in events] == [
        "narration.started",
        "narration.cancelled",
    ]
    assert relay.is_live(INSTITUTION, CLASS) is False


def test_a_stale_generation_or_epoch_cannot_attach():
    relay = NarrationRelay()
    relay.publish(INSTITUTION, CLASS, _base())
    assert relay.attach(
        INSTITUTION, CLASS, actor_epoch=2, min_state_version=1
    ) is None
    assert relay.attach(
        INSTITUTION, CLASS, actor_epoch=1, min_state_version=4
    ) is None
    # A late event from an old generation is ignored, not delivered.
    relay.publish(INSTITUTION, CLASS, _audio(generation=99))
    attachment = relay.attach(
        INSTITUTION, CLASS, actor_epoch=1, min_state_version=3
    )
    assert attachment is not None
    relay.publish(INSTITUTION, CLASS, _completed(sequence=3))
    assert [event["type"] for event in attachment.events()] == [
        "narration.started",
        "narration.completed",
    ]


def test_tenant_is_part_of_the_relay_key():
    relay = NarrationRelay()
    relay.publish(INSTITUTION, CLASS, _base())
    assert relay.attach(
        "other-inst", CLASS, actor_epoch=1, min_state_version=1
    ) is None

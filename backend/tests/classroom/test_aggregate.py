"""V0-010 Classroom Aggregate: the pure reducer (no HTTP, no store).

These are the deterministic unit tests the state machine's "universal transition
contract" demands, run directly against :class:`ClassroomAggregate` with a fixed
clock and a hand-built pinned tuple, so no package, publication or database is
involved: the reducer's behaviour is a pure function of its inputs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.classroom.aggregate import (
    COMMAND_CHECKPOINT,
    COMMAND_END,
    COMMAND_NAVIGATE,
    COMMAND_START,
    EVENT_CHECKPOINT_RECORDED,
    EVENT_SCENE_CHANGED,
    EVENT_SESSION_ENDED,
    EVENT_SESSION_STARTED,
    ClassroomAggregate,
    Command,
)
from app.classroom.errors import (
    ISSUE_INVALID_COMMAND,
    ISSUE_INVALID_TRANSITION,
    ISSUE_STALE_EPOCH,
    ISSUE_STALE_STATE_VERSION,
    SnapshotIntegrityError,
)
from app.classroom.models import CLASSROOM_STATE_ACTIVE, CLASSROOM_STATE_COMPLETED
from app.classroom.snapshot import snapshot_checksum, validate_snapshot

LESSON = {
    "lesson_plan_version": "lpv-1",
    "lesson_id": "lesson-1",
    "section_index": 0,
    "section_id": "section-1",
    "scene_id": "scene-1",
    "scene_step_id": "step-1",
}

FIXED_NOW = datetime(2026, 10, 17, 10, 0, tzinfo=timezone.utc)


def _plan() -> SimpleNamespace:
    return SimpleNamespace(
        institution_id="university-001",
        course_id="course-1",
        class_id="class-1",
        versions={
            "course_id": "course-1",
            "course_version": 1,
            "version_id": "version-1",
            "publication_id": "publication-1",
            "package_id": "package-1",
            "content_package_version": "cpv-1",
            "content_digest": "d" * 64,
            "lesson_plan_version": "lpv-1",
            "knowledge_index_version": "unindexed",
            "index_version_id": "idx-1",
            "index_source_digest": "d" * 64,
            "teaching_graph_version": None,
            "assessment_version": None,
            "model_routing_version": None,
            "policy_version": "runtime-policy@1",
            "capability_version": "local-structural-svg@3.1.0",
            "region": "local-1",
        },
    )


def _aggregate() -> ClassroomAggregate:
    return ClassroomAggregate.session(
        plan=_plan(), session_id="session-1", lesson=LESSON, clock=lambda: FIXED_NOW
    )


def _started_aggregate() -> ClassroomAggregate:
    aggregate = _aggregate()
    result = aggregate.handle(Command.create(COMMAND_START))
    assert result.accepted
    return aggregate


def _navigate(section_index: int = 1, scene_id: str = "scene-2", **extra) -> Command:
    return Command.create(
        COMMAND_NAVIGATE,
        section_index=section_index,
        section_id=extra.pop("section_id", "section-2"),
        scene_id=scene_id,
        scene_step_id=extra.pop("scene_step_id", "step-2"),
        **extra,
    )


# -- the reducer ----------------------------------------------------------------


def test_start_transitions_to_active_and_pins_the_tuple():
    aggregate = _aggregate()
    result = aggregate.handle(Command.create(COMMAND_START))

    assert result.accepted
    assert result.issue_code is None
    assert result.state_version == 1
    assert result.event_sequence == 1
    assert result.events[0].type == EVENT_SESSION_STARTED
    assert aggregate.state == CLASSROOM_STATE_ACTIVE

    document = aggregate.snapshot()
    assert document["state"] == CLASSROOM_STATE_ACTIVE
    assert document["actor_epoch"] == 1
    assert document["state_version"] == 1
    assert document["event_sequence"] == 1
    assert document["versions"]["content_package_version"] == "cpv-1"
    assert document["lesson"]["scene_id"] == "scene-1"
    assert document["turn"] == {"queue": [], "floor": None, "stt_reservation": None}
    assert document["timeline"]["checkpoint"] is None


def test_a_second_start_is_an_invalid_transition():
    aggregate = _started_aggregate()
    result = aggregate.handle(Command.create(COMMAND_START))

    assert not result.accepted
    assert result.issue_code == ISSUE_INVALID_TRANSITION
    assert aggregate.state_version == 1, "a refused command does not advance the version"


def test_navigate_updates_the_scene_and_timeline():
    aggregate = _started_aggregate()
    result = aggregate.handle(_navigate(section_index=1, scene_id="scene-2"))

    assert result.accepted
    assert result.state_version == 2
    assert result.events[0].type == EVENT_SCENE_CHANGED
    assert aggregate.lesson["section_index"] == 1
    assert aggregate.lesson["scene_id"] == "scene-2"
    assert aggregate.timeline["scene_id"] == "scene-2"
    assert aggregate.timeline["step_id"] == "step-2"
    assert aggregate.state == CLASSROOM_STATE_ACTIVE


def test_checkpoint_records_the_current_position():
    aggregate = _started_aggregate()
    result = aggregate.handle(Command.create(COMMAND_CHECKPOINT, label="before student"))

    assert result.accepted
    assert result.events[0].type == EVENT_CHECKPOINT_RECORDED
    checkpoint = aggregate.timeline["checkpoint"]
    assert checkpoint["scene_id"] == "scene-1"
    assert checkpoint["label"] == "before student"
    assert checkpoint["final"] is False
    assert checkpoint["checkpoint_id"]


def test_end_transitions_to_completed_and_records_a_final_checkpoint():
    aggregate = _started_aggregate()
    result = aggregate.handle(Command.create(COMMAND_END))

    assert result.accepted
    assert result.events[0].type == EVENT_SESSION_ENDED
    assert aggregate.state == CLASSROOM_STATE_COMPLETED
    assert aggregate.turn == {"queue": [], "floor": None, "stt_reservation": None}
    assert aggregate.timeline["checkpoint"]["final"] is True


def test_navigate_after_end_is_an_invalid_transition():
    aggregate = _started_aggregate()
    assert aggregate.handle(Command.create(COMMAND_END)).accepted
    result = aggregate.handle(_navigate())

    assert not result.accepted
    assert result.issue_code == ISSUE_INVALID_TRANSITION
    assert aggregate.state_version == 2, "end was the only accepted transition"


def test_navigate_without_a_scene_is_an_invalid_command():
    aggregate = _started_aggregate()
    result = aggregate.handle(Command.create(COMMAND_NAVIGATE, section_index=1))

    assert not result.accepted
    assert result.issue_code == ISSUE_INVALID_COMMAND


# -- idempotency and fencing ----------------------------------------------------


def test_a_duplicate_command_has_one_logical_effect():
    aggregate = _started_aggregate()
    command = _navigate()
    first = aggregate.handle(command)
    second = aggregate.handle(command)

    assert first.accepted
    assert second.duplicate is True
    assert second.accepted is True
    assert second.state_version == first.state_version
    assert len(aggregate.events) == 2, "START plus one navigate, not two"


def test_a_duplicate_refused_command_returns_the_same_refusal():
    aggregate = _started_aggregate()
    bad = Command.create(COMMAND_NAVIGATE, section_index=1)  # no scene_id
    first = aggregate.handle(bad)
    second = aggregate.handle(bad)

    assert not first.accepted
    assert second.duplicate is True
    assert not second.accepted
    assert second.issue_code == ISSUE_INVALID_COMMAND
    assert aggregate.state_version == 1


def test_a_stale_state_version_is_fenced():
    aggregate = _started_aggregate()
    result = aggregate.handle(_navigate(expected_state_version=99))

    assert not result.accepted
    assert result.issue_code == ISSUE_STALE_STATE_VERSION
    assert aggregate.state_version == 1
    assert aggregate.lesson["scene_id"] == "scene-1", "the stale command changed nothing"


def test_a_stale_epoch_is_fenced():
    aggregate = _started_aggregate()
    result = aggregate.handle(_navigate(expected_actor_epoch=7))

    assert not result.accepted
    assert result.issue_code == ISSUE_STALE_EPOCH
    assert aggregate.state_version == 1


# -- snapshot round trip and corruption ----------------------------------------


def test_snapshot_round_trip_restores_pinned_tuple_and_position():
    aggregate = _started_aggregate()
    aggregate.handle(_navigate(section_index=2, scene_id="scene-3"))
    aggregate.handle(Command.create(COMMAND_CHECKPOINT, label="resume"))

    restored = ClassroomAggregate.restore(aggregate.snapshot(), clock=lambda: FIXED_NOW)

    assert restored.state_version == aggregate.state_version
    assert restored.event_sequence == aggregate.event_sequence
    assert restored.versions == aggregate.versions
    assert restored.lesson == aggregate.lesson
    assert restored.timeline == aggregate.timeline
    assert snapshot_checksum(restored.snapshot()) == snapshot_checksum(aggregate.snapshot())


def test_a_corrupted_snapshot_is_refused():
    document = _started_aggregate().snapshot()

    missing = {key: value for key, value in document.items() if key != "versions"}
    with pytest.raises(SnapshotIntegrityError):
        ClassroomAggregate.restore(missing)

    bad_schema = {**document, "schema_version": "runtime-snapshot@99"}
    with pytest.raises(SnapshotIntegrityError):
        ClassroomAggregate.restore(bad_schema)

    with pytest.raises(SnapshotIntegrityError):
        validate_snapshot(document, checksum="0" * 64)

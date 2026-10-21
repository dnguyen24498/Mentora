"""The in-process Classroom Aggregate (V0-010).

``DEC-RUNTIME-001``: *"One logical classroom has one serialized authoritative
state owner called Classroom Actor."* This module is that owner in its pure,
deterministic form: a :class:`ClassroomAggregate` is the single reducer for a
session's state. It accepts commands, fences stale ones, applies the transition,
emits the event, and produces the durable snapshot.

The design mirrors the state machine
(``docs/state-machines/CLASSROOM_SESSION_STATE_MACHINE.md``):

```text
(NEW) --START--> ACTIVE --NAVIGATE/CHECKPOINT--> ACTIVE
                ACTIVE/DEGRADED --END--> COMPLETED --REOPEN--> ACTIVE
```

``ENDING`` is in-process only and is never persisted (the same reasoning as
``PREPARING``/``SEALING``/``INDEXING``/``COMMITTING``): an ``END`` commits the
``ACTIVE -> COMPLETED`` change and its final checkpoint in one snapshot, so a
crash mid-end is indistinguishable from one that never ended.

``REOPEN`` continues an ended **class occurrence**: it keeps the pinned tuple and
returns to the first lesson position, so the teacher can run the same lesson again
without losing the roster. It starts a new actor epoch, which is what makes every
join credential issued before the end stale (``DEC-RUNTIME-007``); the old
snapshots remain durable history and a new one is appended.

Three properties are structural, not advisory:

* **Command idempotency is the aggregate's memory** (``DEC-RUNTIME-003``). A
  command id that has already been handled — accepted *or* rejected — returns the
  stored terminal result and changes nothing. The memory is in-process: durable
  cross-restart dedup is the ordered per-class log's job (``DEC-DATA-003`` is
  ``OPEN``, V1-002), so a restart restores the *state* but not the dedup cache.
* **Epoch and state version fence stale commands** (``DEC-RUNTIME-007``). A
  command naming an ``expected_actor_epoch`` or ``expected_state_version`` that is
  not current is refused without effect, which is how a client that missed
  transitions is told to resync.
* **The snapshot is the aggregate's own serialisation.** ``snapshot()`` is the one
  document (``runtime-snapshot@1``) that both the start and every later transition
  write, so restore-from-snapshot and save-snapshot can never disagree about the
  shape.

Everything is a plain function of its inputs: no clock is read except through the
injected ``clock``, and no provider/IO touches this module (the same rule as the
renderers and the publication service).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from app.classroom.errors import (
    ISSUE_INVALID_COMMAND,
    ISSUE_INVALID_TRANSITION,
    ISSUE_STALE_EPOCH,
    ISSUE_STALE_STATE_VERSION,
)
from app.classroom.models import (
    CLASSROOM_STATE_ACTIVE,
    CLASSROOM_STATE_COMPLETED,
    CLASSROOM_STATE_DEGRADED,
    CLASSROOM_STATE_ENDING,
    CLASSROOM_STATE_FAILED,
    INITIAL_ACTOR_EPOCH,
    SNAPSHOT_SCHEMA_VERSION,
)
from app.classroom.snapshot import validate_snapshot

#: The command vocabulary (``docs/architecture/08_RUNTIME_CONTROL_PLANE.md``:
#: start/end, scene navigation, checkpoint). Raise Hand and the turn/floor
#: commands are V1-003/V1-004 and are deliberately absent.
COMMAND_START = "START"
COMMAND_NAVIGATE = "NAVIGATE_SCENE"
COMMAND_CHECKPOINT = "CHECKPOINT"
COMMAND_END = "END"
COMMAND_REOPEN = "REOPEN"

#: The events each accepted command emits. These are the in-process event names;
#: the wire event schemas (``contracts/events/``) are V1-002's.
EVENT_SESSION_STARTED = "classroom.session.started"
EVENT_SCENE_CHANGED = "classroom.scene.changed"
EVENT_CHECKPOINT_RECORDED = "classroom.checkpoint.recorded"
EVENT_SESSION_ENDED = "classroom.session.ended"
EVENT_SESSION_REOPENED = "classroom.session.reopened"

#: States that a navigation/checkpoint/end command may be applied from.
_MUTABLE_STATES: tuple[str, ...] = (CLASSROOM_STATE_ACTIVE, CLASSROOM_STATE_DEGRADED)

#: States a session cannot continue from: no floor, no queued turn.
_TERMINAL_STATES: tuple[str, ...] = (
    CLASSROOM_STATE_ENDING,
    CLASSROOM_STATE_COMPLETED,
    CLASSROOM_STATE_FAILED,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Command:
    """A serialized instruction with a stable id and optional fencing hints.

    ``command_id`` is the idempotency key. ``expected_actor_epoch`` and
    ``expected_state_version`` are the caller's view of the state; when present and
    stale, the command is refused rather than misapplied (``DEC-RUNTIME-007``).
    """

    command_id: str
    type: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    expected_actor_epoch: Optional[int] = None
    expected_state_version: Optional[int] = None
    principal_id: Optional[str] = None
    issued_at: Optional[str] = None

    @classmethod
    def create(
        cls,
        type: str,
        *,
        command_id: Optional[str] = None,
        expected_actor_epoch: Optional[int] = None,
        expected_state_version: Optional[int] = None,
        principal_id: Optional[str] = None,
        issued_at: Optional[str] = None,
        **payload: Any,
    ) -> "Command":
        return cls(
            command_id=command_id or str(uuid.uuid4()),
            type=type,
            payload=dict(payload),
            expected_actor_epoch=expected_actor_epoch,
            expected_state_version=expected_state_version,
            principal_id=principal_id,
            issued_at=issued_at,
        )


@dataclass(frozen=True)
class Event:
    """One ordered effect of an accepted command (``DEC-DATA-003``'s unit)."""

    event_id: str
    type: str
    sequence: int
    state_version: int
    actor_epoch: int
    occurred_at: str
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "type": self.type,
            "sequence": self.sequence,
            "state_version": self.state_version,
            "actor_epoch": self.actor_epoch,
            "occurred_at": self.occurred_at,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class CommandResult:
    """The terminal verdict of a command: accepted, or refused with a reason.

    A duplicate command returns the original verdict with ``duplicate=True`` and
    the original ``state_version``/``event_sequence`` — it changed nothing.
    """

    command_id: str
    accepted: bool
    issue_code: Optional[str]
    state_version: int
    event_sequence: int
    events: tuple[Event, ...]
    duplicate: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "accepted": self.accepted,
            "issue_code": self.issue_code,
            "state_version": self.state_version,
            "event_sequence": self.event_sequence,
            "duplicate": self.duplicate,
            "events": [event.to_dict() for event in self.events],
        }


class AggregateIntegrityError(Exception):
    """A post-transition invariant is broken (a bug, not a client's refusal)."""


class _Rejected(Exception):
    """Internal: a command is refused with a precise ``issue_code``."""

    def __init__(self, issue_code: str) -> None:
        super().__init__(issue_code)
        self.issue_code = issue_code


class ClassroomAggregate:
    """The single reducer for one session's authoritative state."""

    def __init__(
        self,
        *,
        institution_id: str,
        course_id: str,
        class_id: str,
        session_id: str,
        actor_epoch: int,
        state_version: int,
        event_sequence: int,
        versions: Mapping[str, Any],
        lesson: Mapping[str, Any],
        turn: Mapping[str, Any],
        timeline: Mapping[str, Any],
        pending_effects: list[Any],
        state: Optional[str],
        clock: Optional[Any] = None,
    ) -> None:
        self.institution_id = institution_id
        self.course_id = course_id
        self.class_id = class_id
        self.session_id = session_id
        self.actor_epoch = int(actor_epoch)
        self.state_version = int(state_version)
        self.event_sequence = int(event_sequence)
        self.versions = dict(versions)
        self.lesson = dict(lesson)
        self.turn = dict(turn)
        self.timeline = dict(timeline)
        self.pending_effects = list(pending_effects)
        self.state = state
        self._clock = clock or _utcnow
        # In-process idempotency memory (DEC-RUNTIME-003); V1-002 makes it durable.
        self._handled: dict[str, CommandResult] = {}
        self._events: list[Event] = []

    # -- construction -------------------------------------------------------------
    @classmethod
    def session(
        cls,
        *,
        plan: Any,
        session_id: str,
        lesson: Mapping[str, Any],
        actor_epoch: int = INITIAL_ACTOR_EPOCH,
        clock: Optional[Any] = None,
    ) -> "ClassroomAggregate":
        """A not-yet-started session; ``START`` is its first command.

        The pinned tuple and the first lesson position come from the start's
        resolution (``ClassroomService.start_class``), so the aggregate stays a
        pure reducer over resolved values — it never resolves anything itself.
        """

        return cls(
            institution_id=plan.institution_id,
            course_id=plan.course_id,
            class_id=plan.class_id,
            session_id=session_id,
            actor_epoch=actor_epoch,
            state_version=0,
            event_sequence=0,
            versions=plan.versions,
            lesson=dict(lesson),
            turn={"queue": [], "floor": None, "stt_reservation": None},
            timeline={
                "scene_id": lesson.get("scene_id"),
                "step_id": lesson.get("scene_step_id"),
                "checkpoint": None,
            },
            pending_effects=[],
            state=None,
            clock=clock,
        )

    @classmethod
    def restore(cls, document: Mapping[str, Any], *, clock: Optional[Any] = None) -> "ClassroomAggregate":
        """Rebuild from a durable snapshot (``DEC-DATA-004``: validated first)."""

        validate_snapshot(document)
        return cls(
            institution_id=document["institution_id"],
            course_id=document["course_id"],
            class_id=document["class_id"],
            session_id=document["session_id"],
            actor_epoch=document["actor_epoch"],
            state_version=document["state_version"],
            event_sequence=document["event_sequence"],
            versions=document["versions"],
            lesson=document["lesson"],
            turn=document["turn"],
            timeline=document["timeline"],
            pending_effects=document["pending_effects"],
            state=document["state"],
            clock=clock,
        )

    # -- command handling ---------------------------------------------------------
    def handle(self, command: Command) -> CommandResult:
        """Deduplicate, fence, transition, then check invariants — in that order."""

        cached = self._handled.get(command.command_id)
        if cached is not None:
            return CommandResult(
                command_id=command.command_id,
                accepted=cached.accepted,
                issue_code=cached.issue_code,
                state_version=cached.state_version,
                event_sequence=cached.event_sequence,
                events=cached.events,
                duplicate=True,
            )

        refusal = self._fence(command)
        if refusal is not None:
            result = CommandResult(
                command_id=command.command_id,
                accepted=False,
                issue_code=refusal,
                state_version=self.state_version,
                event_sequence=self.event_sequence,
                events=(),
            )
            self._handled[command.command_id] = result
            return result

        try:
            event = self._transition(command)
        except _Rejected as exc:
            result = CommandResult(
                command_id=command.command_id,
                accepted=False,
                issue_code=exc.issue_code,
                state_version=self.state_version,
                event_sequence=self.event_sequence,
                events=(),
            )
            self._handled[command.command_id] = result
            return result

        self.state_version += 1
        self.event_sequence += 1
        self._events.append(event)
        self._assert_invariants()

        result = CommandResult(
            command_id=command.command_id,
            accepted=True,
            issue_code=None,
            state_version=self.state_version,
            event_sequence=self.event_sequence,
            events=(event,),
        )
        self._handled[command.command_id] = result
        return result

    def snapshot(self) -> dict[str, Any]:
        """The durable document this aggregate serialises to (and restores from)."""

        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "institution_id": self.institution_id,
            "course_id": self.course_id,
            "class_id": self.class_id,
            "session_id": self.session_id,
            "state": self.state,
            "actor_epoch": self.actor_epoch,
            "state_version": self.state_version,
            "event_sequence": self.event_sequence,
            "versions": dict(self.versions),
            "lesson": dict(self.lesson),
            "turn": dict(self.turn),
            "timeline": dict(self.timeline),
            "pending_effects": list(self.pending_effects),
        }

    @property
    def events(self) -> tuple[Event, ...]:
        """The events applied so far, in order (observability and tests)."""

        return tuple(self._events)

    # -- internals -----------------------------------------------------------------
    def _fence(self, command: Command) -> Optional[str]:
        if (
            command.expected_actor_epoch is not None
            and command.expected_actor_epoch != self.actor_epoch
        ):
            return ISSUE_STALE_EPOCH
        if (
            command.expected_state_version is not None
            and command.expected_state_version != self.state_version
        ):
            return ISSUE_STALE_STATE_VERSION
        return None

    def _transition(self, command: Command) -> Event:
        if command.type == COMMAND_START:
            return self._start()
        if command.type == COMMAND_NAVIGATE:
            return self._navigate(command.payload)
        if command.type == COMMAND_CHECKPOINT:
            return self._checkpoint(command.payload)
        if command.type == COMMAND_END:
            return self._end()
        if command.type == COMMAND_REOPEN:
            return self._reopen(command.payload)
        raise _Rejected(ISSUE_INVALID_COMMAND)

    def _start(self) -> Event:
        if self.state is not None:
            raise _Rejected(ISSUE_INVALID_TRANSITION)
        self.state = CLASSROOM_STATE_ACTIVE
        return self._event(EVENT_SESSION_STARTED, {"state": CLASSROOM_STATE_ACTIVE})

    def _navigate(self, payload: Mapping[str, Any]) -> Event:
        if self.state not in _MUTABLE_STATES:
            raise _Rejected(ISSUE_INVALID_TRANSITION)
        section_index = payload.get("section_index")
        scene_id = payload.get("scene_id")
        if not isinstance(section_index, int) or section_index < 0:
            raise _Rejected(ISSUE_INVALID_COMMAND)
        if not isinstance(scene_id, str) or not scene_id:
            raise _Rejected(ISSUE_INVALID_COMMAND)
        scene_step_id = payload.get("scene_step_id")
        previous = {
            "section_index": self.lesson.get("section_index"),
            "section_id": self.lesson.get("section_id"),
            "scene_id": self.lesson.get("scene_id"),
            "scene_step_id": self.lesson.get("scene_step_id"),
        }
        self.lesson["section_index"] = section_index
        self.lesson["section_id"] = payload.get("section_id")
        self.lesson["scene_id"] = scene_id
        self.lesson["scene_step_id"] = scene_step_id
        self.timeline["scene_id"] = scene_id
        self.timeline["step_id"] = scene_step_id
        return self._event(
            EVENT_SCENE_CHANGED,
            {
                "from": previous,
                "to": {
                    "section_index": section_index,
                    "section_id": payload.get("section_id"),
                    "scene_id": scene_id,
                    "scene_step_id": scene_step_id,
                },
            },
        )

    def _checkpoint(self, payload: Mapping[str, Any]) -> Event:
        if self.state not in _MUTABLE_STATES:
            raise _Rejected(ISSUE_INVALID_TRANSITION)
        checkpoint = self._build_checkpoint(label=payload.get("label"), final=False)
        self.timeline["checkpoint"] = checkpoint
        return self._event(EVENT_CHECKPOINT_RECORDED, {"checkpoint": checkpoint})

    def _end(self) -> Event:
        if self.state not in _MUTABLE_STATES:
            raise _Rejected(ISSUE_INVALID_TRANSITION)
        # ``CLASS_END``: stop accepting turns, revoke, persist final checkpoint.
        self.turn["queue"] = []
        self.turn["floor"] = None
        self.turn["stt_reservation"] = None
        checkpoint = self._build_checkpoint(label="class-ended", final=True)
        self.timeline["checkpoint"] = checkpoint
        self.state = CLASSROOM_STATE_COMPLETED
        return self._event(EVENT_SESSION_ENDED, {"final_checkpoint": checkpoint})

    def _reopen(self, payload: Mapping[str, Any]) -> Event:
        """``COMPLETED -> ACTIVE`` for a new run of the same class occurrence.

        The pinned tuple is untouched (``DEC-CONTENT-005``), the roster stays with
        the class, and the lesson returns to the first section so automatic play
        has somewhere to go. The epoch is bumped **before** the event is built, so
        every credential and every fenced command issued before the end belongs to
        a stale epoch (``DEC-RUNTIME-007``); old snapshots are still valid history.
        """

        if self.state != CLASSROOM_STATE_COMPLETED:
            raise _Rejected(ISSUE_INVALID_TRANSITION)
        section_index = payload.get("section_index")
        scene_id = payload.get("scene_id")
        if not isinstance(section_index, int) or section_index < 0:
            raise _Rejected(ISSUE_INVALID_COMMAND)
        if not isinstance(scene_id, str) or not scene_id:
            raise _Rejected(ISSUE_INVALID_COMMAND)
        previous_epoch = self.actor_epoch
        previous_scene_id = self.lesson.get("scene_id")

        self.actor_epoch += 1
        self.state = CLASSROOM_STATE_ACTIVE
        self.turn = {"queue": [], "floor": None, "stt_reservation": None}
        self.lesson.update(
            {
                "lesson_plan_version": payload.get("lesson_plan_version"),
                "lesson_id": payload.get("lesson_id"),
                "section_index": section_index,
                "section_id": payload.get("section_id"),
                "scene_id": scene_id,
                "scene_step_id": payload.get("scene_step_id"),
            }
        )
        self.timeline["scene_id"] = scene_id
        self.timeline["step_id"] = payload.get("scene_step_id")
        self.timeline["checkpoint"] = None
        return self._event(
            EVENT_SESSION_REOPENED,
            {
                "state": CLASSROOM_STATE_ACTIVE,
                "previous_state": CLASSROOM_STATE_COMPLETED,
                "previous_actor_epoch": previous_epoch,
                "actor_epoch": self.actor_epoch,
                "previous_scene_id": previous_scene_id,
                "scene_id": scene_id,
                "section_index": section_index,
            },
        )

    def _build_checkpoint(self, *, label: Optional[str], final: bool) -> dict[str, Any]:
        return {
            "checkpoint_id": str(uuid.uuid4()),
            "scene_id": self.lesson.get("scene_id"),
            "step_id": self.lesson.get("scene_step_id"),
            "label": label,
            "final": final,
            "created_at": self._clock().isoformat(),
        }

    def _event(self, type_: str, payload: Mapping[str, Any]) -> Event:
        return Event(
            event_id=str(uuid.uuid4()),
            type=type_,
            sequence=self.state_version + 1,
            state_version=self.state_version + 1,
            actor_epoch=self.actor_epoch,
            occurred_at=self._clock().isoformat(),
            payload=dict(payload),
        )

    def _assert_invariants(self) -> None:
        """The post-transition checks the state machine makes mandatory."""

        if self.state_version < 0 or self.event_sequence < 0:
            raise AggregateIntegrityError("counters cannot be negative")
        if self.state is None:
            if self.state_version != 0:
                raise AggregateIntegrityError("an unstarted session has state version 0")
            return
        if self.state_version < 1 or self.event_sequence < 1:
            raise AggregateIntegrityError("a started session counts from 1")
        floor = self.turn.get("floor")
        if floor is not None and self.state != CLASSROOM_STATE_ACTIVE:
            raise AggregateIntegrityError("a non-active state has no valid floor")
        if self.turn.get("stt_reservation") is not None and floor is None:
            raise AggregateIntegrityError("an STT reservation implies a floor")
        if self.state in _TERMINAL_STATES:
            if floor is not None or self.turn.get("queue"):
                raise AggregateIntegrityError("a terminal state has no floor or queue")


__all__ = [
    "COMMAND_CHECKPOINT",
    "COMMAND_END",
    "COMMAND_NAVIGATE",
    "COMMAND_REOPEN",
    "COMMAND_START",
    "EVENT_CHECKPOINT_RECORDED",
    "EVENT_SCENE_CHANGED",
    "EVENT_SESSION_ENDED",
    "EVENT_SESSION_REOPENED",
    "EVENT_SESSION_STARTED",
    "AggregateIntegrityError",
    "ClassroomAggregate",
    "Command",
    "CommandResult",
    "Event",
]

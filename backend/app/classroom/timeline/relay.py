"""In-process live narration relay (development bridge).

The teacher's narrated stage is the only place a scene is synthesized. Students
must not trigger a second synthesis for the same slide: that would multiply provider
work per learner and let each student drift to their own audio. This module mirrors
the teacher's already-generated semantic chunks to the students attached to the
class, so everyone hears the same WAV chunks the teacher's stream produced.

It is deliberately **not** the media plane. The canonical architecture moves shared
classroom audio over the SFU (V1-005) and the ordered per-class event log is
``DEC-DATA-003``/``DEC-TECH-004`` (both ``OPEN``). Until then this relay is an
in-process, best-effort bridge for one process — the same shape the voice mock has
under ``DEC-TECH-007``. It is keyed by ``(institution_id, class_id)`` so a tenant
boundary is never crossed in memory.

Lifecycle:

* the teacher's stream publishes ``narration.started``; the relay becomes active for
  that class and remembers the start event, the current ``generation`` and the
  events produced so far;
* every later event for that generation is appended to the generation buffer and
  copied to each attached subscriber's bounded queue (a slow subscriber is dropped
  rather than blocking the teacher);
* a ``narration.completed`` event is delivered as the generation's terminal verdict
  and the completed generation stays replayable for a short TTL. A student who
  attaches while the teacher is still speaking — or just after the teacher's fast
  local mock has synthesized the whole slide — therefore hears **that slide from its
  start** instead of silence. The current slide is the unit of replay; a new slide's
  ``narration.started`` supersedes it (old subscribers receive a synthetic
  cancellation), so a student never hears a slide under a different slide's image.
* an ``error``/explicit ``narration.cancelled`` closes the generation immediately;
  an aborted teacher stream (pause, slide change, tab closed) is closed by
  :meth:`finish` with a synthetic cancellation.

The replay TTL is short (default two minutes) and only applies while the class is
still running. ``after_generation`` lets a client that already consumed a generation
attach again without replaying the same slide while it waits for the teacher's next
one; ``expected_scene_id`` keeps the audio aligned with the slide the student's
authoritative snapshot shows.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

#: Event types that end one narration generation.
_TERMINAL = frozenset({"narration.completed", "narration.cancelled", "error"})

#: The one terminal that leaves the generation replayable for a late student.
_REPLAYABLE = "narration.completed"


@dataclass(eq=False)
class _Subscriber:
    """One attached HTTP response, with a bounded queue the teacher never waits on.

    Identity equality matters: two students may share no fields, but each is a
    distinct attachment in the channel's set.
    """

    queue: "queue.Queue[Any]"
    overflow: bool = False


@dataclass
class _Channel:
    """The current narration generation of one class, with its replay buffer."""

    generation: Optional[int] = None
    start_event: Optional[dict[str, Any]] = None
    last_event: Optional[dict[str, Any]] = None
    buffer: list[dict[str, Any]] = field(default_factory=list)
    terminal: Optional[dict[str, Any]] = None
    terminal_at: Optional[float] = None
    active: bool = False
    actor_epoch: int = 0
    state_version: int = 0
    session_id: str = ""
    scene_id: str = ""
    subscribers: set[_Subscriber] = field(default_factory=set)


class NarrationAttachment:
    """The events one student's HTTP response may read.

    The attachment is single-consumer. It first yields the generation's buffered
    events (start event, the chunks produced before the attach, and a terminal if the
    generation already finished), then every live event published after the attach,
    and ends at the terminal event. Buffering separately from the live queue is what
    lets a late student hear the current slide from its start without a huge live
    queue or a replay that the teacher's next slide cannot supersede.
    """

    def __init__(
        self,
        relay: "NarrationRelay",
        key: tuple[str, str],
        subscriber: _Subscriber,
        buffered: tuple[dict[str, Any], ...],
        start_event: dict[str, Any],
    ) -> None:
        self._relay = relay
        self._key = key
        self._subscriber = subscriber
        self._buffered = buffered
        self.start_event = start_event
        self._closed = False

    def events(self) -> Iterator[dict[str, Any]]:
        try:
            for event in self._buffered:
                yield event
                if event.get("type") in _TERMINAL:
                    return
            while not self._closed:
                if self._subscriber.overflow:
                    return
                try:
                    item = self._subscriber.queue.get(timeout=0.5)
                except queue.Empty:
                    # A blank NDJSON line keeps the response readable (so a proxy
                    # does not time it out) and gives Starlette a chance to notice
                    # a disconnected student even when the teacher's synthesis is
                    # slow. The client ignores blank lines by design.
                    yield {}
                    continue
                if self._subscriber.overflow:
                    return
                yield item
                if item.get("type") in _TERMINAL:
                    return
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._relay._detach(self._key, self._subscriber)


class NarrationRelay:
    """Fan the teacher's narration out to attached students, in one process."""

    def __init__(
        self,
        *,
        queue_size: int = 64,
        replay_ttl_seconds: float = 120.0,
    ) -> None:
        self._lock = threading.Lock()
        self._channels: dict[tuple[str, str], _Channel] = {}
        self._queue_size = max(8, int(queue_size))
        self._replay_ttl = max(0.0, float(replay_ttl_seconds))
        # Completed generations expire lazily on the next publish/attach. Sweep
        # the whole map periodically so a class that never speaks again does not
        # retain its slide buffer forever in a long-lived process.
        self._last_sweep = 0.0
        self._sweep_interval = 30.0

    # -- producer side ----------------------------------------------------------
    def publish(
        self,
        institution_id: str,
        class_id: str,
        event: dict[str, Any],
    ) -> None:
        """Publish one event from the teacher's synthesis stream.

        A ``narration.started`` event opens a new generation. Events from a
        superseded generation are ignored, so a late worker cannot speak over the
        teacher's current slide (``DEC-RUNTIME-007``).
        """

        event_type = str(event.get("type") or "")
        generation = _int(event.get("generation"))
        if generation is None:
            return
        key = (institution_id, class_id)
        with self._lock:
            self._maybe_sweep_locked()
            channel = self._channels.setdefault(key, _Channel())
            self._expire_locked(channel)

            if event_type == "narration.started":
                if channel.active and channel.generation != generation:
                    self._close_locked(channel)
                if channel.active and channel.generation == generation:
                    # A duplicate start for the same generation is the same
                    # presentation; do not reset the buffer or subscribers.
                    return
                channel.generation = generation
                channel.start_event = dict(event)
                channel.last_event = dict(event)
                channel.buffer = [dict(event)]
                channel.terminal = None
                channel.terminal_at = None
                channel.active = True
                channel.actor_epoch = _int(event.get("actor_epoch")) or 0
                channel.state_version = _int(event.get("state_version")) or 0
                channel.session_id = str(event.get("session_id") or "")
                channel.scene_id = str(event.get("scene_id") or "")
                return

            if not channel.active or channel.generation != generation:
                return
            channel.last_event = dict(event)
            channel.buffer.append(dict(event))
            self._deliver_locked(channel, event)
            if event_type in _TERMINAL:
                if event_type == _REPLAYABLE:
                    # The completed slide remains attachable for late students
                    # while the teacher is still playing it. Existing subscribers
                    # already have the terminal in their queue and end there.
                    channel.terminal = dict(event)
                    channel.terminal_at = time.monotonic()
                    channel.subscribers.clear()
                else:
                    # An error/cancellation has nothing to replay; the student
                    # waits for the teacher's next generation.
                    self._reset_locked(channel)

    def finish(
        self,
        institution_id: str,
        class_id: str,
        generation: Optional[int],
    ) -> None:
        """Close ``generation`` if it is still active and did not complete.

        Called from the teacher stream's ``finally``. A normally completed
        generation stays replayable; an aborted one (pause, slide change,
        disconnect) sends attached students a synthetic cancellation so their audio
        stops with the teacher's.
        """

        if generation is None:
            return
        key = (institution_id, class_id)
        with self._lock:
            channel = self._channels.get(key)
            if not channel or not channel.active or channel.generation != generation:
                return
            if channel.terminal is not None:
                # A completed slide is intentionally left for replay.
                return
            cancelled = _cancelled_event(channel)
            self._deliver_locked(channel, cancelled)
            self._reset_locked(channel)

    # -- consumer side ----------------------------------------------------------
    def attach(
        self,
        institution_id: str,
        class_id: str,
        *,
        actor_epoch: int,
        min_state_version: int,
        after_generation: Optional[int] = None,
        expected_scene_id: Optional[str] = None,
    ) -> Optional[NarrationAttachment]:
        """Attach to the class's current generation, or return ``None``.

        ``min_state_version`` is the authoritative state version the caller just
        read. An older generation belongs to a slide the teacher has already left,
        so it is not attached; the caller answers ``204`` and retries. This is the
        same fencing that keeps a late teacher request from speaking over a newer
        slide, applied to listeners.

        ``after_generation`` means "I have already consumed this exact generation";
        it lets the page wait for the next slide instead of replaying the one it just
        heard. ``expected_scene_id`` ties the audio to the slide the student's
        snapshot is showing, so a completed previous slide cannot be replayed under
        a new slide's image.
        """

        key = (institution_id, class_id)
        with self._lock:
            self._maybe_sweep_locked()
            channel = self._channels.get(key)
            if channel is None:
                return None
            self._expire_locked(channel)
            if (
                not channel.active
                or channel.start_event is None
                or channel.generation is None
            ):
                return None
            if channel.actor_epoch != actor_epoch:
                return None
            if channel.state_version < min_state_version:
                return None
            if after_generation is not None and channel.generation == after_generation:
                return None
            if expected_scene_id and channel.scene_id != expected_scene_id:
                return None
            subscriber = _Subscriber(queue.Queue(maxsize=self._queue_size))
            channel.subscribers.add(subscriber)
            return NarrationAttachment(
                self,
                key,
                subscriber,
                tuple(dict(event) for event in channel.buffer),
                dict(channel.start_event),
            )

    def is_live(self, institution_id: str, class_id: str) -> bool:
        """Whether the teacher is currently speaking (not merely replayable)."""

        with self._lock:
            channel = self._channels.get((institution_id, class_id))
            return bool(channel and channel.active and channel.terminal is None)

    def listener_count(self, institution_id: str, class_id: str) -> int:
        """How many responses are attached to the current generation (diagnostics/tests)."""

        with self._lock:
            channel = self._channels.get((institution_id, class_id))
            return len(channel.subscribers) if channel else 0

    # -- internals --------------------------------------------------------------
    def _maybe_sweep_locked(self) -> None:
        now = time.monotonic()
        if now - self._last_sweep < self._sweep_interval:
            return
        self._last_sweep = now
        for key, channel in list(self._channels.items()):
            expired = (
                channel.terminal_at is not None
                and now - channel.terminal_at >= self._replay_ttl
            )
            idle = not channel.active and channel.generation is None
            if expired or idle:
                self._reset_locked(channel)
                self._channels.pop(key, None)

    def _deliver_locked(self, channel: _Channel, event: dict[str, Any]) -> None:
        for subscriber in tuple(channel.subscribers):
            if subscriber.overflow:
                continue
            try:
                subscriber.queue.put_nowait(event)
            except queue.Full:
                # A stalled student must never slow the teacher's synthesis. Drop
                # the subscriber's backlog; its response ends and the page can
                # attach again to the current live position.
                subscriber.overflow = True

    def _close_locked(self, channel: _Channel) -> None:
        cancelled = _cancelled_event(channel)
        self._deliver_locked(channel, cancelled)
        self._reset_locked(channel)

    def _reset_locked(self, channel: _Channel) -> None:
        channel.active = False
        channel.generation = None
        channel.start_event = None
        channel.last_event = None
        channel.terminal = None
        channel.terminal_at = None
        channel.buffer = []
        channel.actor_epoch = 0
        channel.state_version = 0
        channel.session_id = ""
        channel.scene_id = ""
        channel.subscribers.clear()

    def _expire_locked(self, channel: _Channel) -> bool:
        if channel.terminal_at is None:
            return False
        if time.monotonic() - channel.terminal_at < self._replay_ttl:
            return False
        self._reset_locked(channel)
        return True

    def _detach(self, key: tuple[str, str], subscriber: _Subscriber) -> None:
        with self._lock:
            channel = self._channels.get(key)
            if channel is not None:
                channel.subscribers.discard(subscriber)


def _cancelled_event(channel: _Channel) -> dict[str, Any]:
    """A schema-shaped cancellation built from the generation's common envelope.

    It deliberately keeps only the envelope fields the event contract requires:
    carrying the last chunk's ``data``/``text`` into a cancellation would tell a
    late listener that an audio payload belongs to a CANCELLED verdict.
    """

    source = channel.last_event or channel.start_event or {}
    event = {
        key: source[key]
        for key in (
            "schema_version",
            "sequence",
            "class_id",
            "session_id",
            "scene_id",
            "actor_epoch",
            "state_version",
            "generation",
        )
        if key in source
    }
    event.update(
        {
            "schema_version": event.get("schema_version", "1.0"),
            "type": "narration.cancelled",
            "status": "CANCELLED",
            "duration_ms": _int(source.get("duration_ms")) or 0,
        }
    )
    return event


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = ["NarrationAttachment", "NarrationRelay"]

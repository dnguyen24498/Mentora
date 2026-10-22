"""Background presentation of a started class (development bridge).

Before V0-028 the teacher's classroom tab was both the presentation clock and the
synthesis trigger: it asked for a scene's narration, played it, and sent the next
``NAVIGATE_SCENE``. Closing that tab stopped the lesson for everyone.

This module moves the clock to the **API process**. A started class gets one
in-process runner that reads the authoritative snapshot, synthesizes the current
pinned scene through the same provider-neutral
:class:`~app.classroom.timeline.service.TimelineService` the teacher used, publishes
the generation into the class
:class:`~app.classroom.timeline.relay.NarrationRelay`, waits for the scene's audio
to finish, and then moves the aggregate to the next pinned scene. Students keep
hearing and following the lesson even when no teacher tab is open.

It is deliberately **not** the durable scheduler/workflow the canonical
architecture requires. ``DEC-TECH-003`` (durable workflow/scheduler) is ``OPEN`` and
``DEC-TECH-004`` (shared media plane) is ``OPEN``/V1-005, so this is a
single-process, best-effort development bridge:

* the runner lives in the API process; an API restart loses it, and a teacher can
  start it again with ``POST /classes/{classId}/presentation/resume``;
* audio distribution is still the HTTP relay, not the SFU;
* the runner reads only the session's **pinned** package (``DEC-CONTENT-005``) and
  mutates the class only through the aggregate's normal ``NAVIGATE_SCENE`` command
  (fenced by ``state_version``, ``DEC-RUNTIME-007``).

A teacher may pause/resume the class-level presentation. Pausing cancels any
in-flight provider generation and freezes the position; resuming starts the current
scene from its beginning — a semantic segment, never a byte offset
(``DEC-RUNTIME-005``). The relay may already have delivered a fully synthesized
slide, so a browser can still drain buffered audio: pausing a live media stream is
the SFU's job (``DEC-TECH-004``), not this in-process bridge's.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Optional

from app.classroom.models import (
    CLASSROOM_STATE_ACTIVE,
    CLASSROOM_STATE_COMPLETED,
    CLASSROOM_STATE_DEGRADED,
    CLASSROOM_STATE_ENDING,
    CLASSROOM_STATE_FAILED,
)
from app.classroom.scene_source import PinnedSceneSummary
from app.classroom.service import ClassroomService
from app.classroom.timeline.service import TimelineService
from app.speech.port import CancelToken

logger = logging.getLogger(__name__)

#: The states in which a lesson is actually being presented.
_RUNNING = frozenset({CLASSROOM_STATE_ACTIVE, CLASSROOM_STATE_DEGRADED})

#: A state that means the occurrence is over (or being torn down). The presenter
#: stops rather than waiting for a teacher reopen; the reopen command starts a new
#: runner through the HTTP route.
_STOPPED = frozenset(
    {
        CLASSROOM_STATE_ENDING,
        CLASSROOM_STATE_FAILED,
        CLASSROOM_STATE_COMPLETED,
    }
)

#: A text-paced scene (empty script or speech fallback) still needs a dwell. These
#: mirror the client's V0-026 rule: 5 s floor, 30 s cap, at a default pace.
DEFAULT_TEACHING_WPM = 160
MIN_TEXT_DWELL_MS = 5_000
MAX_TEXT_DWELL_MS = 30_000


@dataclass(frozen=True)
class PresentationStatus:
    """What the teacher's page needs to describe/control the background runner."""

    class_id: str
    available: bool
    running: bool
    paused: bool
    at_end: bool
    scene_order: Optional[int] = None
    scene_id: Optional[str] = None
    actor_epoch: Optional[int] = None
    state_version: Optional[int] = None
    issue_code: Optional[str] = None
    message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "class_id": self.class_id,
            "available": self.available,
            "running": self.running,
            "paused": self.paused,
            "at_end": self.at_end,
            "scene_order": self.scene_order,
            "scene_id": self.scene_id,
            "actor_epoch": self.actor_epoch,
            "state_version": self.state_version,
            "issue_code": self.issue_code,
            "message": self.message,
        }


@dataclass(frozen=True)
class _Observation:
    """The authoritative position at one instant."""

    state: str
    actor_epoch: int
    state_version: int
    scene_id: str
    section_index: int
    scene_step_id: Optional[str]
    order: int
    scenes: tuple[PinnedSceneSummary, ...]

    @property
    def ended(self) -> bool:
        return self.state in _STOPPED

    @property
    def running(self) -> bool:
        return self.state in _RUNNING

    @property
    def key(self) -> tuple[Any, ...]:
        # The state version is intentionally absent: a checkpoint or metadata
        # change must not restart the audio, while a manual navigation to another
        # scene (or a new epoch) does.
        return (
            self.actor_epoch,
            self.scene_id,
            self.section_index,
            self.scene_step_id,
        )


class ClassroomPresenter:
    """Own the in-process background runner for every started class.

    ``start`` is idempotent per class. ``stop`` removes the runner; ``pause`` and
    ``resume`` control the current one. A class that ended loses its runner, and a
    reopen starts a fresh one through the router.
    """

    def __init__(
        self,
        classroom: ClassroomService,
        timeline: TimelineService,
        *,
        tick_seconds: float = 0.2,
        grace_seconds: float = 0.5,
        teaching_wpm: int = DEFAULT_TEACHING_WPM,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._classroom = classroom
        self._timeline = timeline
        self._tick = max(0.05, float(tick_seconds))
        self._grace = max(0.0, float(grace_seconds))
        self._wpm = max(1, int(teaching_wpm))
        self._clock = clock
        self._lock = threading.Lock()
        self._runners: dict[tuple[str, str], _PresentationRunner] = {}

    # -- control surface --------------------------------------------------------
    def start(self, institution_id: str, class_id: str) -> PresentationStatus:
        """Start (or leave running) the class's background presentation."""

        key = (institution_id, class_id)
        with self._lock:
            runner = self._runners.get(key)
            if runner is not None and runner.alive:
                return runner.status()
            runner = _PresentationRunner(
                presenter=self,
                institution_id=institution_id,
                class_id=class_id,
                classroom=self._classroom,
                timeline=self._timeline,
                tick_seconds=self._tick,
                grace_seconds=self._grace,
                teaching_wpm=self._wpm,
                clock=self._clock,
            )
            self._runners[key] = runner
            runner.start()
            return runner.status()

    def stop(self, institution_id: str, class_id: str) -> PresentationStatus:
        """Stop the runner and cancel the current generation. Idempotent."""

        with self._lock:
            runner = self._runners.pop((institution_id, class_id), None)
        if runner is not None:
            runner.stop()
        return self.status(institution_id, class_id)

    def pause(self, institution_id: str, class_id: str) -> PresentationStatus:
        """Pause the class-level presentation (idempotent)."""

        runner = self._runner(institution_id, class_id)
        if runner is None:
            return self.status(institution_id, class_id)
        runner.pause()
        return runner.status()

    def resume(self, institution_id: str, class_id: str) -> PresentationStatus:
        """Resume (or start, after an API restart) the presentation."""

        runner = self._runner(institution_id, class_id)
        if runner is None or not runner.alive:
            return self.start(institution_id, class_id)
        runner.resume()
        return runner.status()

    def status(self, institution_id: str, class_id: str) -> PresentationStatus:
        runner = self._runner(institution_id, class_id)
        if runner is None or not runner.alive:
            return PresentationStatus(
                class_id=class_id,
                available=True,
                running=False,
                paused=False,
                at_end=False,
            )
        return runner.status()

    def close(self) -> None:
        """Stop every runner (application shutdown)."""

        with self._lock:
            runners = list(self._runners.values())
            self._runners.clear()
        for runner in runners:
            runner.stop()

    # -- runner callbacks -------------------------------------------------------
    def _runner(self, institution_id: str, class_id: str) -> Optional["_PresentationRunner"]:
        with self._lock:
            runner = self._runners.get((institution_id, class_id))
            if runner is None or not runner.alive:
                return None
            return runner

    def _forget(self, institution_id: str, class_id: str, runner: "_PresentationRunner") -> None:
        with self._lock:
            if self._runners.get((institution_id, class_id)) is runner:
                self._runners.pop((institution_id, class_id), None)


class _PresentationRunner:
    """One class's presentation loop, owned by :class:`ClassroomPresenter`."""

    def __init__(
        self,
        *,
        presenter: ClassroomPresenter,
        institution_id: str,
        class_id: str,
        classroom: ClassroomService,
        timeline: TimelineService,
        tick_seconds: float,
        grace_seconds: float,
        teaching_wpm: int,
        clock: Callable[[], float],
    ) -> None:
        self._presenter = presenter
        self._institution_id = institution_id
        self._class_id = class_id
        self._classroom = classroom
        self._timeline = timeline
        self._tick = tick_seconds
        self._grace = grace_seconds
        self._wpm = teaching_wpm
        self._clock = clock

        self._stop = threading.Event()
        # ``_resume`` is set while the runner may present; cleared while paused.
        self._resume = threading.Event()
        self._resume.set()
        self._lock = threading.Lock()
        self._cancel_lock = threading.Lock()
        self._cancel: Optional[CancelToken] = None
        self._scene_order: Optional[int] = None
        self._scene_id: Optional[str] = None
        self._actor_epoch: Optional[int] = None
        self._state_version: Optional[int] = None
        self._at_end = False
        self._issue_code: Optional[str] = None
        self._message: Optional[str] = None
        self._scene_cache: Optional[tuple[str, tuple[PinnedSceneSummary, ...]]] = None
        self._thread = threading.Thread(
            target=self._run,
            name=f"presentation-{class_id}",
            daemon=True,
        )

    # -- lifecycle --------------------------------------------------------------
    @property
    def alive(self) -> bool:
        return self._thread.is_alive() and not self._stop.is_set()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._resume.set()
        self._cancel_current()
        # A provider wrapper gets its own bounded join; the runner is a daemon,
        # so a provider that ignores cancellation cannot hold the process open.
        self._thread.join(timeout=2.0)

    def pause(self) -> None:
        self._resume.clear()
        self._cancel_current()

    def resume(self) -> None:
        self._resume.set()

    def status(self) -> PresentationStatus:
        with self._lock:
            return PresentationStatus(
                class_id=self._class_id,
                available=True,
                running=self.alive,
                paused=not self._resume.is_set(),
                at_end=self._at_end,
                scene_order=self._scene_order,
                scene_id=self._scene_id,
                actor_epoch=self._actor_epoch,
                state_version=self._state_version,
                issue_code=self._issue_code,
                message=self._message,
            )

    # -- the loop ---------------------------------------------------------------
    def _run(self) -> None:
        presented_key: Optional[tuple[Any, ...]] = None
        next_order: Optional[int] = None
        try:
            while not self._stop.is_set():
                if not self._resume.is_set():
                    self._wait_for_resume()
                    # A pause aborts the current scene without finishing it.
                    presented_key = None
                    next_order = None
                    continue

                view = self._observe()
                if view is None:
                    self._sleep_interruptible(self._tick)
                    continue
                if view.ended:
                    break
                if not view.running:
                    self._sleep_interruptible(self._tick)
                    continue

                with self._lock:
                    self._actor_epoch = view.actor_epoch
                    self._state_version = view.state_version

                if presented_key != view.key:
                    presented_key = view.key
                    next_order = self._next_order(view)
                    self._mark_position(view)
                    outcome = self._present(view)
                    if outcome == "paused":
                        presented_key = None
                        next_order = None
                        continue
                    if outcome != "done":
                        # A manual navigation (or a stop/end) changed the
                        # authoritative position while the scene was playing.
                        continue
                    if next_order is None:
                        with self._lock:
                            self._at_end = True
                        if self._wait_for_change(view.key):
                            presented_key = None
                            continue
                        break

                    if not self._resume.is_set() or self._stop.is_set():
                        presented_key = None
                        next_order = None
                        continue
                    self._navigate(view, next_order)
                    # The next observation either sees the new scene (and starts
                    # it) or the same one (a lost race, retried below).
                    continue

                # This scene was already presented. At the last slide the runner
                # holds; otherwise a navigation attempt is retried with a fresh
                # snapshot after a short pause.
                if next_order is None:
                    if self._wait_for_change(view.key):
                        presented_key = None
                        continue
                    break

                if not self._resume.is_set() or self._stop.is_set():
                    presented_key = None
                    next_order = None
                    continue
                view = self._observe()
                if view is not None and view.running and view.key == presented_key:
                    self._navigate(view, next_order)
                self._sleep_interruptible(0.5)
        except Exception:  # never let a runner die silently on a broken package
            logger.exception("background presentation failed for class %s", self._class_id)
        finally:
            self._cancel_current()
            self._presenter._forget(self._institution_id, self._class_id, self)

    # -- observation ------------------------------------------------------------
    def _observe(self) -> Optional[_Observation]:
        try:
            snapshot = self._classroom.peek_snapshot(self._institution_id, self._class_id)
        except Exception as exc:  # a damaged snapshot is a named refusal, not a crash
            self._set_issue(getattr(exc, "issue_code", None), str(exc))
            return None
        if snapshot is None:
            return None
        document = snapshot.document
        state = str(document.get("state") or snapshot.state or "")
        if state not in _RUNNING:
            # ``ended`` distinguishes a completed occurrence (stop) from a class
            # that is merely not presenting yet (wait), but both have no scene.
            return _Observation(
                state=state,
                actor_epoch=snapshot.actor_epoch,
                state_version=snapshot.state_version,
                scene_id="",
                section_index=0,
                scene_step_id=None,
                order=-1,
                scenes=(),
            )

        lesson = document.get("lesson") or {}
        scene_id = str(lesson.get("scene_id") or "")
        section_index = _int(lesson.get("section_index")) or 0
        scene_step_id = (
            str(lesson.get("scene_step_id"))
            if lesson.get("scene_step_id") is not None
            else None
        )
        versions = document.get("versions") or {}
        package_id = str(versions.get("package_id") or "")
        scenes = self._scenes(package_id)
        order = _resolve_order(scenes, scene_id, section_index)
        if order is None:
            self._set_issue(
                "INCOMPATIBLE_CONTENT",
                f"the pinned package has no scene named {scene_id!r}",
            )
            return None
        self._set_issue(None, None)
        return _Observation(
            state=state,
            actor_epoch=snapshot.actor_epoch,
            state_version=snapshot.state_version,
            scene_id=scene_id,
            section_index=section_index,
            scene_step_id=scene_step_id,
            order=order,
            scenes=scenes,
        )

    def _scenes(self, package_id: str) -> tuple[PinnedSceneSummary, ...]:
        with self._lock:
            cached = self._scene_cache
        if cached is not None and cached[0] == package_id:
            return cached[1]
        _plan, scenes = self._classroom.pinned_scenes(
            self._institution_id, self._class_id
        )
        with self._lock:
            self._scene_cache = (package_id, scenes)
        return scenes

    def _next_order(self, view: _Observation) -> Optional[int]:
        later = [scene.order for scene in view.scenes if scene.order > view.order]
        return min(later) if later else None

    # -- one scene --------------------------------------------------------------
    def _present(self, view: _Observation) -> str:
        """Synthesize/relay one scene, wait its playout, then return a verdict.

        ``done`` means the scene finished (the caller may advance); ``paused`` means
        a teacher paused it; ``changed`` means a manual navigation/end changed the
        authoritative position and the loop must re-observe; ``stopped`` means the
        runner is shutting down.
        """

        try:
            read = self._timeline.read(
                self._institution_id,
                self._class_id,
                view.order,
                expected_state_version=view.state_version,
            )
        except Exception as exc:
            # A manual navigation between the observation and the read is a race,
            # not a failure: re-observe. A package/state refusal is surfaced.
            issue = getattr(exc, "issue_code", None)
            if issue not in {"STALE_STATE_VERSION"}:
                self._set_issue(issue, str(exc))
            return "changed"

        token = CancelToken()
        self._set_cancel(token)
        started_at = self._clock()
        first_audio_at: Optional[float] = None
        last_audio_at: Optional[float] = None
        total_ms = 0
        verdict: Optional[str] = None
        last_key_check = started_at
        events = self._timeline.stream(
            read,
            institution_id=self._institution_id,
            class_id=self._class_id,
            cancel=token,
        )
        try:
            for event in events:
                if self._stop.is_set():
                    token.cancel()
                    return "stopped"
                if not self._resume.is_set():
                    token.cancel()
                    return "paused"
                event_type = event.get("type")
                if event_type == "audio":
                    now = self._clock()
                    first_audio_at = first_audio_at or now
                    last_audio_at = now
                    total_ms += max(0, _int(event.get("duration_ms")) or 0)
                elif event_type == "narration.completed":
                    verdict = str(event.get("status") or "")
                    total_ms = max(total_ms, _int(event.get("duration_ms")) or 0)
                now = self._clock()
                if now - last_key_check >= self._tick:
                    last_key_check = now
                    if self._position_changed(view.key):
                        token.cancel()
                        return "changed"
        finally:
            try:
                close = getattr(events, "close", None)
                if close is not None:
                    close()
            finally:
                self._set_cancel(None)

        if self._stop.is_set():
            return "stopped"
        if not self._resume.is_set():
            return "paused"
        if self._position_changed(view.key):
            return "changed"

        if verdict == "COMPLETED" and first_audio_at is not None and total_ms > 0:
            # A student may attach after the fast local synthesis has produced
            # every chunk; the slide stays replayable while this deadline runs.
            playout_end = max(first_audio_at + total_ms / 1000.0, last_audio_at or 0)
            deadline = playout_end + self._grace
        else:
            # Empty script, speech fallback, or a failed provider: keep the
            # lesson moving at a text pace rather than stopping on a silent input.
            deadline = started_at + _text_dwell_seconds(read.script.word_count, self._wpm)
        return self._wait_until(deadline, view.key)

    def _wait_until(self, deadline: float, key: tuple[Any, ...]) -> str:
        while True:
            if self._stop.is_set():
                return "stopped"
            if not self._resume.is_set():
                return "paused"
            if self._position_changed(key):
                return "changed"
            remaining = deadline - self._clock()
            if remaining <= 0:
                return "done"
            # Wait on the stop event so a shutdown is immediate, but cap the
            # interval so a pause/navigation is noticed promptly.
            self._stop.wait(min(self._tick, remaining))

    def _position_changed(self, key: tuple[Any, ...]) -> bool:
        view = self._observe()
        if view is None or view.ended or not view.running:
            return True
        return view.key != key

    def _wait_for_change(self, key: tuple[Any, ...]) -> bool:
        """Wait at the last slide. True means re-observe; False means stop."""

        while not self._stop.is_set():
            if not self._resume.is_set():
                self._wait_for_resume()
                continue
            if self._position_changed(key):
                return True
            self._stop.wait(self._tick)
        return False

    def _wait_for_resume(self) -> None:
        while not self._stop.is_set() and not self._resume.is_set():
            self._resume.wait(0.2)

    # -- navigation / control ---------------------------------------------------
    def _navigate(self, view: _Observation, order: int) -> bool:
        try:
            outcome = self._classroom.navigate_to_order(
                self._institution_id,
                self._class_id,
                order=order,
                command_id=str(uuid.uuid4()),
                expected_state_version=view.state_version,
            )
        except Exception as exc:
            issue = getattr(exc, "issue_code", None)
            if issue not in {"STALE_STATE_VERSION"}:
                self._set_issue(issue, str(exc))
            return False
        if not outcome.result.accepted:
            issue = outcome.result.issue_code
            if issue not in {"STALE_STATE_VERSION"}:
                self._set_issue(issue, None)
            return False
        snapshot = outcome.snapshot
        if snapshot is not None:
            with self._lock:
                self._state_version = snapshot.state_version
                self._actor_epoch = snapshot.actor_epoch
                self._scene_order = order
                self._at_end = False
        self._set_issue(None, None)
        return True

    def _mark_position(self, view: _Observation) -> None:
        with self._lock:
            self._scene_order = view.order
            self._scene_id = view.scene_id
            self._actor_epoch = view.actor_epoch
            self._state_version = view.state_version
            self._at_end = False
            self._issue_code = None
            self._message = None

    def _set_issue(self, issue_code: Optional[str], message: Optional[str]) -> None:
        with self._lock:
            self._issue_code = issue_code
            self._message = message

    def _set_cancel(self, token: Optional[CancelToken]) -> None:
        with self._cancel_lock:
            previous = self._cancel
            self._cancel = token
        if previous is not None and previous is not token and token is None:
            # The stream's own finally is authoritative; this is only a hint to a
            # provider wrapper that may still be finishing.
            previous.cancel()

    def _cancel_current(self) -> None:
        with self._cancel_lock:
            token = self._cancel
        if token is not None:
            token.cancel()

    def _sleep_interruptible(self, seconds: float) -> None:
        self._stop.wait(max(0.0, seconds))


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_order(
    scenes: tuple[PinnedSceneSummary, ...], scene_id: str, section_index: int
) -> Optional[int]:
    matches = [scene for scene in scenes if scene.scene_id == scene_id]
    if not matches:
        return None
    return min(matches, key=lambda scene: abs(scene.order - section_index)).order


def _text_dwell_seconds(words: int, wpm: int) -> float:
    """The V0-026 text-paced dwell, ported to the server clock."""

    if words <= 0:
        return MIN_TEXT_DWELL_MS / 1000.0
    milliseconds = (words / max(1, wpm)) * 60_000.0
    clamped = min(MAX_TEXT_DWELL_MS, max(MIN_TEXT_DWELL_MS, milliseconds))
    return clamped / 1000.0


__all__ = [
    "ClassroomPresenter",
    "PresentationStatus",
    "DEFAULT_TEACHING_WPM",
]

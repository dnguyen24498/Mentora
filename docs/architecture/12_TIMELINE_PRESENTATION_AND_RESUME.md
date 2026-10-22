# Timeline, Presentation, and Resume

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Coordinate speech, visuals, cancellation, and semantic continuation.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Use marker priority: native TTS marker, forced alignment, audio PTS, estimated offset, segment fallback. Presentation events include deadline policy and target version. Client ignores duplicate/stale generations/events and reports sequence gaps.

Audio cancellation names cancel-through generation; client stops/clears/discards/ACKs. Checkpoint precedes student invitation. Resume validates versions/checkpoint, restores presentation, generates bridge phrase, and starts new segment/generation.

## Locked Decisions Implemented

- `DEC-RUNTIME-005`
- `DEC-RUNTIME-006`
- `DEC-TURN-007`

## Implemented narration (V0-013)

The presentation pipeline narrates each pinned slide: pinned script → word-safe
chunks → provider-neutral voice → one WAV per chunk, played in order as it arrives,
and the slide advances when its narration has been heard. Speech failure shows the
authored text and paces the slide by its length (`DEC-TURN-009`). A slide change,
pause or end aborts the stream and cancels synthesis; resuming restarts the current
slide as a new generation. The teacher-scoped
`GET /classes/{classId}/narration/{order}` stream remains available as a manual
preview, but it is no longer the normal producer: since V0-028 the class server's
background presenter reads the same timeline.

An enrolled student's page attaches to the current **live generation** through an
in-process relay (`GET /classes/{classId}/narration`): it starts no synthesis and
copies the same WAV chunks, so a class does not pay one provider call per learner.
The relay is a V1-005 bridge, not the media plane — it is single-process and
best-effort, returns `204` while there is no current generation (the page retries),
ends at each generation's terminal verdict, and sends attached listeners a
cancellation when the presenter pauses or moves. The current slide is the unit of
replay: a late joiner receives the buffered chunks from that slide's start, so the
fast local mock — which can synthesize a whole slide before the student's next
attach — does not leave the class in silence, and the next slide supersedes it. A
completed generation stays replayable for a short TTL; the page passes
`after_generation` so waiting for the next slide does not replay the one it just
heard, and `expected_scene_id` keeps the audio under the slide the authoritative
snapshot shows. A student joining mid-slide is therefore aligned with the displayed
slide but may be a few seconds behind the presenter's own playout.
`DEC-TECH-004` remains `OPEN`; a multi-worker deployment needs the ordered/shared
path that decision will choose, not this in-memory relay. Students see the slide
with no transcript by default (a collapsed accessibility disclosure keeps the text
available) and can enable sound if the browser blocks autoplay.

## Background presentation (V0-028)

A started class is presented by the **API process**, not by the teacher's browser
tab. `backend/app/classroom/timeline/presenter.py` holds one runner per
`(institution, class)`:

- `POST /classes/{id}/start` and `POST /classes/{id}/reopen` schedule the runner
  after the response, so it can never race the transaction that wrote the start or
  reopen snapshot.
- The runner reads only the session's **pinned** package (`DEC-CONTENT-005`),
  synthesizes the current scene through the same `TimelineService` and publishes it
  into the class relay, then waits for its playout. It advances the class through
  the aggregate's normal `NAVIGATE_SCENE` command, fenced by
  `expected_state_version` (`DEC-RUNTIME-007`); it never writes state directly.
- Playout waits `max(first_audio_at + total_audio_ms, last_audio_at) + grace` for a
  completed generation. An empty script, a speech fallback or a failed provider
  uses a text dwell of 5–30 s at 160 wpm so the lesson keeps moving instead of
  stopping in silence.
- A teacher's pause is class-level: it cancels any **in-flight** provider
  generation (listeners receive the relay's cancellation for it) and freezes the
  position. Resume starts the current scene from its beginning — a semantic
  segment, never a byte offset (`DEC-RUNTIME-005`). The HTTP relay may already have
  delivered a fully synthesized slide to a browser, so audio already buffered there
  can still drain; retroactively pausing a media stream is the SFU's job
  (`DEC-TECH-004`/V1-005), not this bridge's.
- A manual `POST /classes/{id}/navigate` is observed by the runner, which aborts the
  old generation and starts the newly authoritative scene. A completed generation
  that is still current remains replayable to a late listener.
- At the last pinned slide the runner **holds** (`at_end`) rather than ending the
  class or looping. Ending (`POST /classes/{id}/end`) stops it synchronously, so
  no further scene is presented; reopening starts a fresh runner at the first slide
  of the new epoch.
- `GET /classes/{id}/presentation`, `POST .../presentation/pause` and
  `POST .../presentation/resume` are the teacher's `class:write` control/status
  surface. `resume` also recovers an `ACTIVE` class after an API restart: the
  runner is in-process and not durable, so the teacher's page offers **Start
  presentation** when `running` is false.

This is explicitly a **development bridge**. `DEC-TECH-003` (durable
workflow/scheduler) is `OPEN`, so the runner is single-process and lost on restart;
`DEC-TECH-004`/V1-005 mean audio still travels over the HTTP relay, not the SFU.
`MENTORA_BACKGROUND_PRESENTATION=0` disables it and the presentation routes report
`available: false`. The teacher's page follows the authoritative snapshot by a
quiet ~1.5 s poll and plays the relay without starting a second synthesis (V0-028).
The client-local V0-026 autoplay pacing is no longer used.

# Timeline State Machine

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define authoritative transitions and failure handling.

## Dependencies

- `docs/architecture/02_ARCHITECTURAL_INVARIANTS.md`
- `docs/architecture/09_CLASSROOM_ACTOR_AND_RECOVERY.md`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

## States and flow

```text
READY -> RUNNING -> PAUSING -> PAUSED -> RESUMING -> RUNNING/COMPLETED. Late events follow execute/skip/coalesce/block. Checkpoint occurs before floor invitation.
```

## Universal transition contract

Command ID deduplication, authorization, expected epoch/state, preconditions, transition, emitted event, effects with idempotency IDs, deadline/timeout, compensation/recovery, and post-transition invariant check are mandatory. Timeouts are explicit ordered inputs.

## Requirement Trace

- `DEC-RUNTIME-003`
- `DEC-RUNTIME-007`
- `DEC-DATA-004`

## Implemented (V0-013)

`backend/app/classroom/timeline/` implements the `TimelineController` for V0:
`IDLE → PREPARING → SYNTHESIZING → PLAYING → COMPLETED`, with `CANCELLED`,
`FAILED` and `FALLBACK` terminal. One generation per narration request; a
different generation is stale, a repeated marker/chunk is a duplicate, a marker
behind the last one or after a terminal verdict is late, and an audio gap raises
rather than splicing. A checkpoint records scene/segment/chunk/offset (semantic,
not bytes); resume starts a new generation at that segment. The script is read from
the pinned package and cut into word-safe chunks (≤160 characters, closed at a
sentence end once ≥40), each synthesized separately so the first audio arrives
after one chunk. The teacher-scoped
`GET /classes/{classId}/narration/{order}` stream remains a manual preview.

Since V0-028 the normal producer is the class server's **background presenter**
(`backend/app/classroom/timeline/presenter.py`). It is started after a class start
or reopen, reads only the pinned package, drives the same timeline over the current
scene, publishes into the relay, waits for playout and then advances the aggregate
through the ordinary fenced `NAVIGATE_SCENE` command. Its pause cancels any
in-flight generation (audio the relay already delivered may finish); resume starts
the current scene from its beginning (semantic, not a byte offset). At the last
slide it holds (`at_end`); `END` stops it before the response, and `REOPEN` starts
a fresh runner in the new epoch. The `class:write` status/control routes are
`GET /classes/{classId}/presentation`, `POST .../presentation/pause` and
`POST .../presentation/resume`; `resume` also recovers a runner lost to an API
restart. A duplicate command is ignored by id
(`DEC-RUNTIME-003`) and a stale position/epoch is refused (`DEC-RUNTIME-007`).

An enrolled student's page (and an open teacher page) attaches to the same live
generation over `GET /classes/{classId}/narration`, an in-process relay that starts
no synthesis, answers `204` while there is no current generation, replays the
current slide's buffered events to a late joiner, and ends at each generation's
terminal verdict. A completed generation remains replayable for a short TTL;
`after_generation` suppresses replaying the one the page already heard and
`expected_scene_id` keeps the audio under the scene the snapshot shows. This is a
V1-005 bridge, not the SFU; `DEC-TECH-004` remains `OPEN`. The presenter itself is
a single-process development bridge, not the durable scheduler `DEC-TECH-003`
leaves `OPEN`; it does not survive an API restart and does not run with
`MENTORA_BACKGROUND_PRESENTATION=0`. The provider is the neutral deterministic mock
(`DEC-TECH-007` `OPEN`), with the opt-in OmniVoice prototype as the same kind of
labelled stand-in.

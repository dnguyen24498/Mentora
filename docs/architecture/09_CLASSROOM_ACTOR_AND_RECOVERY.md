# Classroom Actor and Recovery

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Specify ownership, fencing, snapshots, replay, and reconnect.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Commands for a class are serialized by `class_id`. Ownership acquisition increments actor epoch. State version increments per accepted transition. Downstream tokens/effects carry epoch and deterministic IDs.

Snapshot contains all orthogonal state regions, versions, lesson/scene/step, queue/floor, timeline checkpoint, pending effects, epoch/version/sequence, schema version, and checksum. Recovery restores, replays, reconciles, revokes stale floor, and resyncs clients using snapshot plus deltas.

## Implemented aggregate

The Classroom Actor's deterministic core is implemented in `backend/app/classroom/aggregate.py` (`ClassroomAggregate`, `Command`, `Event`, `CommandResult`), driven by the service's command entry points (`ClassroomService.navigate_scene` / `record_checkpoint` / `end_class`) and persisted by `ClassRepository.commit_transition`. It is an **in-process** reducer — one aggregate instance per class, cached by the service with a per-class lock (`DEC-RUNTIME-001`), and the durable store stays the truth: every accepted transition appends a validated snapshot and updates the session counters in one transaction, guarded by a `WHERE state = ? AND state_version = ? AND actor_epoch = ?` clause, so a writer that lost a race reloads and re-handles instead of clobbering (`DEC-RUNTIME-007`). The commands are `START`, `NAVIGATE_SCENE`, `CHECKPOINT` and `END`; each accepted command emits one event (`classroom.session.started`, `classroom.scene.changed`, `classroom.checkpoint.recorded`, `classroom.session.ended`) and increments `state_version` and `event_sequence` together. Handling runs in the state machine's order: **command-id dedup first** (a replayed command returns its stored terminal verdict and writes nothing — `DEC-RUNTIME-003`), then epoch fencing, then state-version fencing, then the transition, then the post-transition invariant check (a non-active state has no valid floor or queued turn; an STT reservation implies a floor; at most one floor). `START` is the aggregate's own first command: `start_class` builds the session, runs `START`, and commits the snapshot the aggregate produced, so *all* classroom mutations pass through the one reducer. `END` transitions `ACTIVE/DEGRADED -> COMPLETED` (`ENDING` is in-process only, never persisted), records the final checkpoint and revokes the session's live join credentials, so a class end leaks no token. `restore` validates schema version and checksum before use, so a corrupted snapshot is refused rather than replayed (`DEC-DATA-004`); a restart therefore restores the pinned tuple and the scene position from the newest snapshot, and the next command continues from that version. Idempotency memory is in-process — durable cross-restart dedup and the ordered per-class event log/outbox are `DEC-DATA-003`'s open technology and V1-002's ("actor epoch event outbox and replay"), so `DEC-TECH-001`/`DEC-TECH-002` remain `OPEN` and no broker or actor framework is assumed. Tests: `backend/tests/classroom/test_aggregate.py` (the reducer: start, invalid transition, duplicate command, stale epoch/version fencing, snapshot round trip, corrupted snapshot) and `backend/tests/classroom/test_classroom_commands.py` (navigation/checkpoint/end persisting through the aggregate, restart restoring pinned tuple and scene position, a duplicate command writing one snapshot, and a stale command writing nothing).

## Locked Decisions Implemented

- `DEC-RUNTIME-001`
- `DEC-RUNTIME-003`
- `DEC-RUNTIME-004`
- `DEC-RUNTIME-007`
- `DEC-DATA-003`
- `DEC-DATA-004`

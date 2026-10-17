# V0-010: In-process Classroom Aggregate

**Week:** W5  
**Status:** DONE  
**Owner:** Solo developer  
**Target:** V0

## Objective

Implement deterministic single-session state with commands, events, invariants, and snapshots.

## Dependencies

- V0-009

## Requirement IDs

- `DEC-RUNTIME-001`
- `DEC-RUNTIME-003`
- `DEC-RUNTIME-004`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/08_RUNTIME_CONTROL_PLANE.md`
- `docs/architecture/09_CLASSROOM_ACTOR_AND_RECOVERY.md`
- `docs/state-machines/CLASSROOM_SESSION_STATE_MACHINE.md`
- `contracts/snapshots/classroom-snapshot.schema.json`

## In Scope

- Aggregate handle/apply/validate/snapshot.
- Start/end, scene navigation, checkpoint commands/events.
- State version and command dedup.
- Snapshot persistence/restore.

## Out of Scope

- Distributed ownership.
- Message broker.
- Raise Hand.

## Acceptance Criteria

- All classroom mutations pass through aggregate.
- Duplicate command has one logical effect.
- Restart restores pinned tuple and scene position.

## Required Tests

- Reducer tests, invalid transition, duplicate command, snapshot round trip, corrupted snapshot.

## Files/Areas Allowed to Change

- `backend/app/classroom/`
- `backend/tests/classroom/`
- `database/`
- `governance/TRACEABILITY_MATRIX.csv`

## Quality Gate

All tests pass; no architecture contradiction; telemetry and traceability are updated; no new production dependency without an accepted ADR.

## Completion Evidence

- Link to commit/PR: (set after commit; see `STATUS.yaml`)
- Test command and result: `cd backend && env -u PYTHONPATH .venv/bin/python -m pytest -q` → **426 passed** (was 405; +21: 13 reducer tests + 8 integration tests in `backend/tests/classroom/`).
- Demo recording/screenshot: service-level command demo (no new HTTP route — the aggregate is in-process; the frontend shell is V0-011): start → `navigate_scene` → `record_checkpoint` → `end_class`, each committing a new snapshot, then a fresh app instance restoring the pinned tuple and scene position and continuing from `state_version` 4.
- Metrics observed: `class.command` events carry command id/type, `accepted`, `duplicate` and `issue_code` (identities only); counters `commands_accepted`, `commands_rejected`, `commands_duplicated`, `scenes_changed`, `checkpoints_recorded`, `sessions_ended`.
- Traceability rows added: `DEC-RUNTIME-001/003/004/007` and `DEC-DATA-004` ← `aggregate.py`, `service.py`, `repository.py`, the two test files; `09_CLASSROOM_ACTOR_AND_RECOVERY.md` now lists `DEC-RUNTIME-003`.
- Known limitations:
  - Idempotency memory is **in-process** (per-app aggregate registry); durable cross-restart dedup and the ordered per-class event log/outbox are `DEC-DATA-003`'s open technology and V1-002's (`DEC-TECH-001/002` stay `OPEN` — no broker/actor framework).
  - The aggregate's command/event objects are internal; the wire command/event schemas (`contracts/commands/`, `contracts/events/`) and the snapshot envelope (`contracts/snapshots/classroom-snapshot.schema.json`) are V1-002's. The durable snapshot stays `runtime-snapshot@1` (V0-009's contracted shape in `contracts/openapi/openapi.yaml`) so no session breaks.
  - `NAVIGATE_SCENE` carries a *resolved* target (the timeline controller/V0-013 resolves it against the pinned lesson plan); the aggregate validates structure and invariants, not content bounds.
  - `DEGRADED`/`RECOVERING`/`FAILED` and the turn/floor commands (Raise Hand) remain V1-003/V1-004.

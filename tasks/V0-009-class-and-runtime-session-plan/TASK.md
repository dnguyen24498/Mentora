# V0-009: Class and runtime session plan

**Week:** W5  
**Status:** DONE  
**Owner:** Solo developer  
**Target:** V0

## Objective

Create class scheduling/start with exact pinned version tuple.

## Dependencies

- V0-008

## Requirement IDs

- `DEC-CONTENT-005`
- `DEC-DATA-005`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/03_DOMAIN_OWNERSHIP_AND_VERSIONING.md`
- `docs/sequences/CLASS_START.md`

## In Scope

- Class/session persistence.
- Resolve exact CTF/content/lesson/index/policy versions.
- Reject draft/incompatible package.
- Initial session state and snapshot.

## Out of Scope

- Group participants.
- SFU room.
- Distributed actor.

## Acceptance Criteria

- No runtime `latest` lookup.
- Pinned tuple survives restart.
- Only authorized enrollment can join.

## Required Tests

- Draft version rejected, incompatible index, duplicate start, cross-tenant join.

## Files/Areas Allowed to Change

- `backend/app/classroom/`
- `database/`
- `contracts/openapi/`
- `tests/integration/`

## Quality Gate

All tests pass; no architecture contradiction; telemetry and traceability are updated; no new production dependency without an accepted ADR.

## Completion Evidence

**Link to commit/PR:** `99e8110`.

**What was built.** `app/classroom/` is a new package: `service.py` (schedule,
start, snapshot read, enroll, join), `repository.py` (tenant-scoped persistence plus
the single start commit and a read-only projection of the publication-owned tables),
`models.py` (Class, Enrollment, RuntimeSessionPlan, ClassroomSession, SessionSnapshot,
BootstrapToken), `catalog.py` (the replaceable runtime catalog), `snapshot.py` (the
initial document, canonical form, validation), `telemetry.py`, `router.py`, `errors.py`.
Eight routes; six tables (`classes`, `enrollments`, `runtime_session_plans`,
`classroom_sessions`, `session_snapshots`, `bootstrap_tokens`) in `app/db/schema.sql`
with `database/migrations/0004_class_and_session_plan.sql` as the PostgreSQL
reference; `contracts/openapi/openapi.yaml`; two new stable `ErrorCode` members; one
new `Settings` field (`home_region`); the implementation note in
`docs/architecture/03_DOMAIN_OWNERSHIP_AND_VERSIONING.md` and the regenerated
`ARCHITECTURE_FULL.md`.

**How each acceptance criterion is met.**

| Criterion | Mechanism |
| --- | --- |
| No runtime `latest` lookup | The tuple is resolved **once**, in `start_class`, and written into an immutable `RuntimeSessionPlan` (`UNIQUE (class_id)`, no update path). After the start transaction no code path asks a publication question again: `GET /classes/{classId}` reads the session's own plan, and `POST .../start` returns it verbatim on a replay. The implicit resolution — the course's current *published* publication — happens only inside the one start. |
| Pinned tuple survives restart | The plan, the session and the snapshot are durable rows; a fresh app instance on the same store reads the same tuple and the same snapshot byte-for-byte, and the idempotent replay still returns the original session. `test_the_pinned_tuple_survives_a_restart` asserts this against a second `create_app` on the same `settings`. |
| Only authorized enrollment can join | `POST /classes/{classId}/bootstrap-token` requires an `ACTIVE` session **and** a tenant-scoped row in `enrollments` for that `(institution, class, student)`; otherwise `403 NOT_ENROLLED`. A class in another institution is not visible at all (`403 TENANT_ACCESS_DENIED`), and the credential itself binds class/student/session/`actor_epoch`/nonce/expiry, stores only its digest, and carries `subscribe` scope only. |

**How the four required tests map.**

| Required test | Test |
| --- | --- |
| Draft version rejected | `test_a_draft_version_is_refused_and_writes_nothing` (an explicitly pinned draft version *and* a course with no published version), `test_a_failed_start_writes_nothing_and_a_retry_succeeds` |
| Incompatible index | `test_an_incompatible_index_pin_is_refused` (a pin whose `source_digest` is not the published content, and one whose `index_version` disagrees with the publication's pin) |
| Duplicate start | `test_a_duplicate_start_returns_the_same_session`, `test_concurrent_starts_create_one_session` |
| Cross-tenant join | `test_join_requires_enrollment`, `test_class_start_is_tenant_isolated` |

**Design decisions worth stating.**

- **`PREPARING` is in-process only, and never persisted** — the same reasoning as
  V0-008's `SEALING`/`INDEXING`/`COMMITTING`. Everything a start writes commits in one
  transaction (`ClassRepository.commit_start`): a guarded
  `UPDATE classes … WHERE state = 'SCHEDULED'` (a `rowcount` of 0 aborts), then the
  plan, the session and the snapshot. So a crash anywhere before, during or after
  resolution leaves the class `SCHEDULED` with no plan, session or snapshot — a
  partial start is invisible by construction rather than by compensation, and the
  retry path is just a second `POST .../start`.
- **Idempotency is the identity of the class, not a guard around it.** A start whose
  class already has a session returns that session with `created: false`;
  `UNIQUE (class_id)` on both the plan and the session is the backstop for a race the
  guarded update missed, and the loser either re-reads the winner or is classified
  `COMMIT_CONFLICT` (`DEC-RUNTIME-003`).
- **The pinned tuple carries *named absences*.** `assessment_version` and
  `model_routing_version` are pinned as explicit nulls because the canonical tuple
  names them and V0 has neither subsystem. Recording the absence means the immutable
  tuple never has to gain a field later — which matters precisely because a pinned
  tuple must never change.
- **The runtime half of the tuple is replaceable infrastructure and is *resolved*
  at start, not configured globally.** `RuntimeCatalog` supplies the policy version
  (`"runtime-policy@1"` — the name of the applied LOCKED default policy set), the
  supported CTF envelope versions and the home region
  (`Settings.home_region`, `MENTORA_HOME_REGION`, default `local-1`);
  `capability_version` is derived from the **observed** identity of the warmed default
  renderer (`name@version`) with the full identity recorded in the plan's
  `capabilities`. `DEC-TECH-009` stays `OPEN`: the region is configuration, never a
  decided geography.
- **A start never parses the source** (`DEC-CONTENT-001`) and never re-renders: it
  reads the *pinned* package (manifest + lesson plan) and re-verifies it against the
  seal (`verify_package`), then reads the pinned knowledge-index record. The index pin
  is checked for *compatibility*, not just presence: the record's `index_version` must
  equal the publication's `knowledge_index_version` **and** its `source_digest` must
  equal the publication's `content_digest` (`DEC-DATA-005`).
- **The classroom layer reads the publication-owned tables and never writes them**,
  the same one-way projection `PublicationRepository` performs for
  `source_artifacts`, so V0-009 does not touch `backend/app/publication/`.
- **Two new stable error codes** (`CLASS_NOT_READY` 409 with `issue_code`, and
  `NOT_ENROLLED` 403). A refused start is never `PUBLICATION_BLOCKED`: that code
  belongs to the publication transition. A damaged snapshot reuses
  `STORAGE_FAILURE` + `SNAPSHOT_INVALID` (the stored record disagrees with its own
  envelope, which is the same class of failure as an unreadable package).
- **No event is emitted for a start.** The ordered per-class log and its outbox are
  `DEC-DATA-003`'s open technology and V1-002's ("actor epoch event outbox and
  replay"), so a start records the resulting state, the snapshot and telemetry —
  which is what `CLASS_START.md` asserts ("every terminal path emits metrics and
  user-visible state").
- **Deviation from the task's allowlist, stated:** `backend/app/api/app.py`,
  `backend/app/common/errors.py`, `backend/app/config.py` and
  `backend/app/db/schema.sql` were edited to wire the new package, add two stable
  error codes, add one settings field, and create the tables (`backend/app/db/schema.sql`
  is the SQLite counterpart of `database/migrations/`, per `AGENTS.md`). The
  allowlist's `tests/integration/` does not exist in this repo; `backend/tests/` is
  its test root (the same nominal-path mapping V0-004…V0-008 use), so the new suite is
  `backend/tests/test_class_start.py`.

**Test command and result.**

```text
cd backend && env -u PYTHONPATH .venv/bin/python -m pytest -q
405 passed  (was 383; +22 in tests/test_class_start.py)
```

**Demo (real reference deck, 16.7 MB, 28 slides).** Driven end to end against a
throwaway data directory (sha256 `d09377c65fa9f49a…`, package `cpv-fd40e629ab70765e`,
28 scenes, 57 files): upload → build → approve → publish → `POST /classes` →
`POST .../start` returns `created: true` with `state ACTIVE`, `actor_epoch 1` and the
pinned tuple (`course_version 1`, the seal's `content_digest 8fa67c343350195b…`,
`lesson_plan_version`, the `unindexed` knowledge-index pin, `runtime-policy@1`,
`local-structural-svg@3.1.0` as the capability identity, region `local-1`), plus a
14-region snapshot whose `lesson.section_index` is 0 with an empty `turn`
(`queue: []`, `floor: null`) and no pending effects — and whose checksum verifies on
read-back (`GET .../snapshot` returned the identical document). A replay returned
`created: false` with the identical session, plan and snapshot. Publishing a
correction (`course_version 2`) left class A's tuple *and* snapshot unchanged
(byte-identical) while a class started afterwards pinned the new publication, and the
old publication is `SUPERSEDED`. An unenrolled student was refused
`403 NOT_ENROLLED`; the issued credential carried `subscribe` scope and
`actor_epoch 1`, and only its digest was stored. A start on an unpublished course was
refused `409 CLASS_NOT_READY` / `VERSION_NOT_PUBLISHED`, and the refusal added **no**
plan/session/snapshot rows (counts: classes 3, plans 2, sessions 2, snapshots 2).

**Metrics observed.** A start emits `class.started` (tenant, class, session,
course/version, package, content package version, index version, policy, capability,
region, epoch, `created`), a replay increments `starts_replayed` and emits the same
event with `created: false`, and every refusal emits `class.start_blocked` with its
`stage` and `issue_code`. Scheduling emits `class.scheduled`; a join emits `class.join`
(`authorized` true/false with `issue_code`). The demo's counters were
`classes_scheduled 3, sessions_started 2, starts_replayed 1, starts_blocked 1,
joins_authorized 1, joins_denied 1, enrollments_created 1, snapshots_read 2,
snapshot_failures 0`. Records carry identities — never the class title, slide text or
notes, which `test_class_telemetry_carries_identities_not_content` asserts.

**Traceability rows added.** `governance/TRACEABILITY_MATRIX.csv`:
`DEC-CONTENT-001` ← `service.py`, `repository.py`;
`DEC-CONTENT-005` ← `models.py`, `repository.py`, `service.py`, `snapshot.py`, the test;
`DEC-RUNTIME-003` ← `repository.py`, `service.py`, the test;
`DEC-RUNTIME-007` ← `models.py`, `service.py`, the test;
`DEC-DATA-004` ← `snapshot.py`, `service.py`, the test;
`DEC-DATA-005` ← `repository.py`, `service.py`, the test;
`DEC-RELIABILITY-002` ← `service.py`, the test;
`DEC-DEPLOY-002` ← `catalog.py`, `config.py`;
`DEC-TURN-001` ← `models.py`, `service.py`.

**Known limitations.**

- **The actor epoch is only the initial one.** Claiming, fencing and transferring
  ownership across an actor failure is V1-002; a join credential is *bound* to
  `actor_epoch` and a stale-epoch token is refused (tested), but nothing yet changes
  or fences the epoch.
- **No scheduler.** `scheduled_for` is recorded and never enforced: a durable
  workflow/scheduler is `DEC-TECH-003` (`OPEN`), so `start` is explicit. A timed
  auto-start is V1+.
- **No event log, no outbox, no event emission for a start** (`DEC-DATA-003`'s open
  technology, V1-002). Recovery-from-replay therefore has its durable snapshot and
  its pinned tuple, but no ordered event stream to replay yet; the snapshot shape
  (`state_version`, `event_sequence`, `pending_effects`, `turn`, `timeline`) is the
  one V0-010/V1-002 will fill.
- **The stages after `ACTIVE` are not implemented.** `DEGRADED`, `RECOVERING`,
  `ENDING`, `COMPLETED` and `FAILED` exist in the vocabulary and in the schema's
  `CHECK`, but only `SCHEDULED -> ACTIVE` is written; V0-010 owns the transitions.
- **Enrollment is the whole authorization story in V0.** Institutional federation,
  roles and service identity (`docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md`)
  do not exist, so `student_id` is client-asserted and enrollment is attribution a
  caller can, in principle, claim for any id it names; the tenant boundary and the
  class roster are real, the principal is not yet.
- **`verify_bootstrap_token` has no HTTP route.** It is the service method the media
  gateway will call in V1 (there is no media plane to call it yet), and the same
  applies to `revoke_bootstrap_token`: the revocation path exists and is tested, but
  no endpoint or gateway exposes it.
- **The snapshot is initial only.** There is no periodic/transition snapshotting and
  no restore path — `GET .../snapshot` validates and returns the stored document, but
  nothing replays it into a live actor.

